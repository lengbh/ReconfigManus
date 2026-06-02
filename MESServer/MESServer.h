//
// Created by bohanleng on 28/10/2025.
//

#ifndef RECONFIGMANUS_MESSERVER_H
#define RECONFIGMANUS_MESSERVER_H

#include "mes_server_def.h"
#include "GraphManager.h"
#include "MQTTServer.h"
#include "OrderManager.h"
#include "ProcessManager.h"
#include <memory>
#include <unordered_map>

class MESServer : public MQTTConn::IMQTTServer
{
    friend class ProcessManager;
    friend class OrderManager;
public:
    MESServer(uint16_t port, const json & j_graph, const json & j_capabilities, const json & j_products,
              std::string broker_host = "localhost");

    ~MESServer();

    void Start();

    // Control policies
    ST_StationActionRsp OnStationActionQuery(const ST_StationActionQuery& qry);
    ST_StationActionRsp OnStationActionDoneQuery(const ST_StationActionQuery& qry);
    bool FindNextStationToTargetStation(const uint32_t & current_station, const uint32_t & target_station, uint32_t & out) const;
    bool PlanRouteToProcessStation(uint32_t current_station, ST_ProcessInfo process, uint32_t & out_next_station) const;
    [[nodiscard]] uint32_t CalculateDefaultNextStation(const uint32_t & current_station) const;

    ST_TrayInfo & GetTrayInfo(uint32_t tray_id);

    void CreateOrderBatch(uint32_t num, uint8_t product_type) const;

    void OnMessage(std::shared_ptr<MQTTConn::IMQTTConn> client, MQTTConn::MQTTMsg & msg) override;

protected:
    std::unique_ptr<GraphManager> graph_manager_;
    std::unique_ptr<ProcessManager> process_manager_;
    std::unique_ptr<OrderManager> order_manager_;

    std::unordered_map<uint32_t, ST_TrayInfo> tray_info_dict_;
};


#endif //RECONFIGMANUS_MESSERVER_H
