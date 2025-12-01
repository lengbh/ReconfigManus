//
// Created by bohanleng on 28/10/2025.
//

#include "MESServer.h"
#include "LogMacros.h"
#include "mes_server_def.h"
#include <memory>

MESServer::MESServer(uint16_t port, const json& j_graph, const json& j_capabilities, const json& j_products, uint8_t product_type)
    : ITCPServer<TCPConn::TCPMsg>(port)
{
    graph_manager_ = std::make_unique<GraphManager>(j_graph);
    graph_manager_->WriteOutDotFile("system_graph.dot");
    process_manager_ = std::make_unique<ProcessManager>(std::shared_ptr<MESServer>(this), j_capabilities, j_products, product_type);
    order_manager_ = std::make_unique<OrderManager>();
}

bool MESServer::OnClientConnectionRequest(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client)
{
    std::cout << "Client " << client->GetID() << " requested\n";
    return true;
}

void MESServer::OnClientConnected(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client)
{
    std::cout << "Client " << client->GetID() << " connected\n";
}

void MESServer::OnClientDisconnected(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client)
{
    ITCPServer<TCPConn::TCPMsg>::OnClientDisconnected(client);
}

void MESServer::OnMessage(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client, TCPConn::TCPMsg& msg)
{
    switch (msg.header.type)
    {
        // TODO
        case MSG_STATION_ACTION_QUERY:
            {
                ST_StationActionQuery qry;
                msg >> qry;
                INFO_MSG("[MES] Action query received: workstation_id: {}, tray_id: {}", qry.workstation_id, qry.tray_id);
                const auto rsp = OnStationActionQuery(qry);
                TCPConn::TCPMsg rsp_msg;
                rsp_msg.header.type = MSG_STATION_ACTION_RSP;
                rsp_msg << rsp;
                client->Send(rsp_msg);
            }
            break;
        case MSG_STATION_ACTION_DONE_QUERY:
            {
                ST_StationActionQuery qry;
                msg >> qry;
                INFO_MSG("[MES] Action done query received: workstation_id: {}, tray_id: {}", qry.workstation_id, qry.tray_id);
                const auto rsp = OnStationActionDoneQuery(qry);
                TCPConn::TCPMsg rsp_msg;
                rsp_msg.header.type = MSG_STATION_ACTION_RSP;
                rsp_msg << rsp;
                client->Send(rsp_msg);
            }
            break;
        default:
            break;
    }

}

ST_StationActionRsp MESServer::OnStationActionQuery(const ST_StationActionQuery& qry)
{
    // Construct default releasing response
    ST_StationActionRsp rsp;
    auto & tray_info = GetTrayInfo(qry.tray_id);
    rsp.qry = qry;
    // Set order_id based on whether the tray has an executing order
    rsp.order_id = tray_info.executing_order ? tray_info.current_order_id : UINT32_MAX;
    rsp.action_type = 0;    // Default action: release
    rsp.next_station_id = CalculateDefaultNextStation(qry.workstation_id);

    if (!tray_info.executing_order)
    {
        // Try assigning order to the tray only if at order assigning station
        if (process_manager_->IsOrderAssigningStation(qry.workstation_id))
        {
            // if no order waiting, release
            if (order_manager_->GetWaitOrderNum() == 0)
            {
                INFO_MSG("[MES] No order waiting, default release.");
                return rsp;
            }
            // Else there are orders waiting, try assign
            uint32_t order_id;
            if (!order_manager_->TryAssignNewOrderToTray(qry.tray_id, order_id))
            {
                // Assigning failed, release
                INFO_MSG("[MES] Assigning order failed, default release.");
                return rsp;
            }
            // Else assigning success
            tray_info.executing_order = true;
            tray_info.current_order_id = order_id;
            rsp.order_id = order_id;

            ST_ProcessInfo process;
            if (!process_manager_->GetNextProcessToExecute(order_id, process))
            {
                ERROR_MSG("[MES] Failed to find the process to execute at station {}", qry.workstation_id);
                return rsp;
            }
            if (!process_manager_->ProcessCanBeExecutedAtStation(process, qry.workstation_id))
            {
                uint32_t next_station = UINT32_MAX;
                if (!PlanRouteToProcessStation(qry.workstation_id, process, next_station))
                {
                    ERROR_MSG("[MES] Cannot plan route to station for next process, default release.");
                    rsp.order_id = UINT32_MAX;
                    return rsp;
                }
                rsp.action_type = 0;
                rsp.next_station_id = next_station;
                INFO_MSG("[MES] Routing tray {} to station {}", qry.tray_id, next_station);
                return rsp;
            }
            // TODO assume for now one station only execute one type of process, so merely returning  1 meaning execute
            rsp.action_type = 1;
            graph_manager_->AddTimeDistToAllPathsToVertex(qry.workstation_id);
            INFO_MSG("[MES] Execute process {} at station {}", process, qry.workstation_id);
            return rsp;
        }
        INFO_MSG("[MES] Tray not at order assigning station, default release.");
        return rsp;
    }
    // Else order executing on the tray
    ST_ProcessInfo process;
    if (!process_manager_->GetNextProcessToExecute(tray_info.current_order_id, process))
    {
        INFO_MSG("[MES] Failed to find the process to execute anymore {}", qry.workstation_id);
        // Treating any type of false return as finished (actually containing error cases)
        order_manager_->UpdateOrderStatus(tray_info.current_order_id);
        tray_info.executing_order = false;
        tray_info.current_order_id = UINT32_MAX;
        rsp.order_id = UINT32_MAX;
        INFO_MSG("[MES] Tray {} status reset", qry.tray_id);
        return rsp;
    }
    if (!process_manager_->ProcessCanBeExecutedAtStation(process, qry.workstation_id))
    {
        uint32_t next_station = UINT32_MAX;
        if (!PlanRouteToProcessStation(qry.workstation_id, process, next_station))
        {
            INFO_MSG("[MES] Cannot plan route to station for next process, default release.");
            return rsp;
        }
        rsp.action_type = 0;
        rsp.next_station_id = next_station;
        INFO_MSG("[MES] Routing tray {} to station {}", qry.tray_id, next_station);
        return rsp;
    }
    // TODO assume for now one station only execute one type of process, so merely returning  1 meaning execute
    rsp.action_type = 1;
    graph_manager_->AddTimeDistToAllPathsToVertex(qry.workstation_id);
    INFO_MSG("[MES] Execute process {} at station {}", process, qry.workstation_id);
    return rsp;
}

ST_StationActionRsp MESServer::OnStationActionDoneQuery(const ST_StationActionQuery& qry)
{
    // Construct default releasing response
    ST_StationActionRsp rsp;
    auto & tray_info = GetTrayInfo(qry.tray_id);
    rsp.qry = qry;
    // Set order_id based on whether the tray has an executing order
    rsp.order_id = tray_info.executing_order ? tray_info.current_order_id : UINT32_MAX;
    rsp.action_type = 0;    // Default action: release
    rsp.next_station_id = CalculateDefaultNextStation(qry.workstation_id);

    if (!tray_info.executing_order)
    {
        // This case shouldn't exist
        ERROR_MSG("[MES] Action done for a non-existing order");
        return rsp;
    }
    Order order;
    if (!order_manager_->GetOrderByID(tray_info.current_order_id, order))
    {
        // This case shouldn't exist
        ERROR_MSG("[MES] Action done for a non-existing order");
        return rsp;
    }
    // TODO for now only consider one process possible for one station
    order_manager_->OnOrderProcessSuccess(tray_info.current_order_id, process_manager_->station_process_map_[qry.workstation_id].front());
    rsp.order_id = UINT32_MAX;
    graph_manager_->AddTimeDistToAllPathsToVertex(qry.workstation_id, false);
    // Hand over to OnStationActionQuery
    return OnStationActionQuery(qry);
}

bool MESServer::FindNextStationToTargetStation(const uint32_t& current_station, const uint32_t& target_station,
                                               uint32_t& out) const
{
    // TODO maybe can be refactored to `GraphManager`c
    // If current_station == target_station, return the same station
    std::vector<uint32_t> path;
    float length;
    if (!graph_manager_->FindShortestPath(current_station, target_station, path, length))
    {
        ERROR_MSG("[Graph] No path from station {} to station {}", current_station, target_station);
        return false;
    }
    if (path.size() >= 2)
        out = path[1];
    else
        out = path.front();
    return true;
}

bool MESServer::PlanRouteToProcessStation(uint32_t current_station, const ST_ProcessInfo process, uint32_t & out_next_station) const
{
    // Next process cannot execute here, find stations available for next process
    std::list<uint32_t> next_stations;
    if (!process_manager_->FindStationsForProcess(process, next_stations))
    {
        ERROR_MSG("[MES] Cannot find stations  available for next process");
        return false;
    }

    // For every possible station, route to the one with the smallest path length
    float best_len = std::numeric_limits<float>::infinity();
    uint32_t best_target = UINT32_MAX;
    for (const auto station_id : next_stations)
    {
        std::vector<uint32_t> path;
        float len = 0.0f;
        if (!graph_manager_->FindShortestPath(current_station, station_id, path, len))
            continue; // unreachable, skip
        if (len < best_len)
        {
            best_len = len;
            best_target = station_id;
        }
    }
    if (best_target == UINT32_MAX)
    {
        ERROR_MSG("[MES] None of the candidate stations is reachable from station {}", current_station);
        return false; // keep default release decision
    }
    uint32_t next_station;
    if (!FindNextStationToTargetStation(current_station, best_target, next_station))
    {
        ERROR_MSG("[MES] Failed to compute next station from {} to {}", current_station, best_target);
        return false;
    }
    out_next_station = next_station;
    return true;
}

uint32_t MESServer::CalculateDefaultNextStation(const uint32_t& current_station) const
{
    // Used for default releasing response when no additional information can be derived
    // By default move to default returning station
    auto returning_station = process_manager_->GetDefaultReturningStation();
    if (current_station != returning_station)
    {
        uint32_t next_station;
        if (!FindNextStationToTargetStation(current_station, returning_station, next_station))
            return UINT32_MAX;
        return next_station;
    }
    // if current station is the default returning station, direct to an arbitrary connected station
    std::list<uint32_t> outgoing_neighbors;
    if (!graph_manager_->GetOutgoingNeighborVertices(current_station, outgoing_neighbors))
    {
        ERROR_MSG("[Graph] No outgoing neighbors from station {}", current_station);
        return UINT32_MAX;
    }
    return outgoing_neighbors.front();
}

ST_TrayInfo& MESServer::GetTrayInfo(uint32_t tray_id)
{
    // Return existing if present; otherwise create with defaults and return
    auto it = tray_info_dict_.find(tray_id);
    if (it != tray_info_dict_.end())
        return it->second;

    auto [ins_it, inserted] = tray_info_dict_.try_emplace(tray_id, ST_TrayInfo{ tray_id, false, UINT32_MAX});
    return ins_it->second;
}

void MESServer::CreateOrderBatch(const uint32_t num) const
{
    auto product_type = process_manager_->product_->product_type;
    for (int i = 0 ; i < num ; i ++)
        order_manager_->CreateNewOrder(product_type);
}