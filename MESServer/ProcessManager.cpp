//
// Created by bohanleng on 09/11/2025.
//

#include "ProcessManager.h"
#include "LogMacros.h"
#include "MESServer.h"
#include <algorithm>

ProcessManager::ProcessManager(const std::shared_ptr<MESServer>& mes_server_ptr, const json& station_cfg, const json & products_cfg, uint8_t product_type)
{
    // TODO check validity of the file
    INFO_MSG("Loading station process configuration...");
    for (const auto & s : station_cfg["stations"])
    {
        // load process_capability
        const uint32_t station_id = s["id"].get<uint32_t>();
        if (s.contains("process_capability"))
        {
            const auto cap_val = static_cast<ST_ProcessInfo>(s["process_capability"].get<uint32_t>());
            station_process_map_[station_id].push_back(cap_val);
        }
        if (s["is_order_assigning_station"].get<bool>())
            order_assigning_stations_.push_back(station_id);
    }

    // Product
    product_ = std::make_unique<Product>(products_cfg, product_type);

    // MES
    mes_server_ = mes_server_ptr;
}

bool ProcessManager::IsOrderAssigningStation(const uint32_t station_id) const
{
    for (const auto & id : order_assigning_stations_)
        if (id == station_id)
            return true;
    return false;
}

bool ProcessManager::GetNextProcessToExecute(const uint32_t order_id, ST_ProcessInfo& out) const
{
    Order order;
    if (!mes_server_->order_manager_->GetOrderByID(order_id, order))
    {
        ERROR_MSG("[Process] order id does not exist");
        return false;
    }
    // Execution not started, return the first process
    if (order.executed_processes.empty())
    {
        ST_ProcessInfo process;
        if (!product_->GetFirstProcess(process))
        {
            ERROR_MSG("[Process] First process does not exist");
            return false;
        }
        out = process;
        return true;
    }
    // Execution ongoing
    std::vector<ST_ProcessInfo> remaining_process;
    if (!product_->GetRemainingProcesses(order, remaining_process))
    {
        INFO_MSG("[Process] Remaining process does not exist");
        return false;
    }
    // TODO Assume only sequential processes supported for now
    const auto process = remaining_process.front();
    out = process;
    return true;
}

bool ProcessManager::ProcessCanBeExecutedAtStation(const ST_ProcessInfo& process, const uint32_t station) const
{
    const auto it = station_process_map_.find(station);
    if (it == station_process_map_.end())
    {
        ERROR_MSG("[Process] station {} not found or has no configured process capability", station);
        return false;
    }

    const auto & capabilities = it->second;
    if (std::find(capabilities.begin(), capabilities.end(), process) == capabilities.end())
    {
        INFO_MSG("[Process] process {} cannot be executed at station {}", process, station);
        return false;
    }
    return true;
}

bool ProcessManager::FindStationsForProcess(const ST_ProcessInfo& process, std::list<uint32_t>& out_stations) const
{
    out_stations.clear();

    for (const auto & entry : station_process_map_)
    {
        const uint32_t station_id = entry.first;
        const auto & capabilities = entry.second;
        if (std::find(capabilities.begin(), capabilities.end(), process) != capabilities.end())
        {
            out_stations.push_back(station_id);
        }
    }

    if (out_stations.empty())
    {
        ERROR_MSG("[Process] No station can execute process {}", process);
        return false;
    }
    return true;
}

uint32_t ProcessManager::GetDefaultReturningStation() const
{
    return order_assigning_stations_.front();
}
