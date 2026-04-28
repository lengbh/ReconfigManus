//
// Created by bohanleng on 09/11/2025.
//

#ifndef RECONFIGMANUS_PROCESSMANAGER_H
#define RECONFIGMANUS_PROCESSMANAGER_H

#include <list>
#include <unordered_map>
#include <memory>
#include "nlohmann/json.hpp"
#include "ProductManager.h"

class MESServer; // forward declaration
using json = nlohmann::json;

class ProcessManager
{
public:
    friend class MESServer;

    ProcessManager(const std::shared_ptr<MESServer>& mes_server_ptr, const json & station_cfg, const json & products_cfg);
    ~ProcessManager() = default;

    bool IsOrderAssigningStation(uint32_t station_id) const;

    bool GetNextProcessToExecute(uint32_t order_id, ST_ProcessInfo& out) const;

    bool ProcessCanBeExecutedAtStation(const ST_ProcessInfo & process, uint32_t station) const;

    bool FindStationsForProcess(const ST_ProcessInfo & process, std::list<uint32_t> & out_stations) const;

    uint32_t GetDefaultReturningStation() const;
    bool HasProduct(uint8_t product_type) const;

protected:
    const Product * GetProduct(uint8_t product_type) const;

    std::shared_ptr<MESServer> mes_server_;

    std::list<uint32_t> order_assigning_stations_;

    std::unordered_map<uint32_t, std::list<ST_ProcessInfo>> station_process_map_;
    std::unordered_map<uint8_t, Product> products_;
};


#endif //RECONFIGMANUS_PROCESSMANAGER_H
