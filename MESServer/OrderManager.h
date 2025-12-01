//
// Created by bohanleng on 04/11/2025.
//

#ifndef RECONFIGMANUS_ORDERMANAGER_H
#define RECONFIGMANUS_ORDERMANAGER_H

#include <atomic>
#include <list>
#include <memory>
#include <queue>
#include <unordered_map>
#include "mes_server_def.h"


struct Order
{
    uint32_t order_id;
    uint8_t product_type;
    uint32_t tray_id;
    ORDER_RUN_STATUS status;
    std::vector<ST_ProcessInfo> executed_processes{};
};

class OrderManager
{
    friend class MES_Server;
public:
    OrderManager() = default;
    ~OrderManager() = default;

    uint32_t CreateNewOrder(uint8_t product_type);

    bool GetOrderByID(uint32_t order_id, Order& order) const;
    size_t GetWaitOrderNum() const;
    bool IsOrderDone(uint32_t order_id);

    bool TryAssignNewOrderToTray(uint32_t tray_id, uint32_t& order_id);
    void OnOrderProcessSuccess(uint32_t order_id, const ST_ProcessInfo& process);
    void UpdateOrderStatus(uint32_t order_id);

protected:

    std::atomic<uint32_t> cur_order_id_ = 0;
    std::unordered_map<uint32_t, Order> order_pool_;

    std::queue<uint32_t> waiting_orders_;
    std::list<uint32_t> running_orders_;
    std::list<uint32_t> finished_orders_;

};


#endif //RECONFIGMANUS_ORDERMANAGER_H