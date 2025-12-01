//
// Created by bohanleng on 28/10/2025.
//

#ifndef RECONFIGMANUS_MESSERVER_H
#define RECONFIGMANUS_MESSERVER_H

#include "TCPServer.h"
#include "mes_server_def.h"
#include "GraphManager.h"
#include "OrderManager.h"
#include "ProcessManager.h"

class MESServer : public TCPConn::ITCPServer<TCPConn::TCPMsg>
{
    friend class ProcessManager;
    friend class OrderManager;
public:
    MESServer(uint16_t port, const json & j_graph, const json & j_capabilities, const json & j_products, uint8_t product_type);

    ~MESServer() override = default;

    // Communication interfaces
    bool OnClientConnectionRequest(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client) override;
    void OnClientConnected(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client) override;
    void OnClientDisconnected(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client) override;
    void OnMessage(std::shared_ptr<TCPConn::ITCPConn<TCPConn::TCPMsg>> client, TCPConn::TCPMsg& msg) override;


    // Control policies
    ST_StationActionRsp OnStationActionQuery(const ST_StationActionQuery& qry);
    ST_StationActionRsp OnStationActionDoneQuery(const ST_StationActionQuery& qry);
    bool FindNextStationToTargetStation(const uint32_t & current_station, const uint32_t & target_station, uint32_t & out) const;
    bool PlanRouteToProcessStation(uint32_t current_station, ST_ProcessInfo process, uint32_t & out_next_station) const;
    [[nodiscard]] uint32_t CalculateDefaultNextStation(const uint32_t & current_station) const;

    ST_TrayInfo & GetTrayInfo(uint32_t tray_id);

    void CreateOrderBatch(uint32_t num) const;

protected:
    std::unique_ptr<GraphManager> graph_manager_;
    std::unique_ptr<ProcessManager> process_manager_;
    std::unique_ptr<OrderManager> order_manager_;

    std::unordered_map<uint32_t, ST_TrayInfo> tray_info_dict_;
};


#endif //RECONFIGMANUS_MESSERVER_H