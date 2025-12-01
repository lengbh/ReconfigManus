//
// Created by bohanleng on 04/11/2025.
//

#include "OrderManager.h"
#include <algorithm>
#include "LogMacros.h"

uint32_t OrderManager::CreateNewOrder(uint8_t product_type)
{
    const uint32_t new_order_id = ++cur_order_id_;
    order_pool_[new_order_id] = Order{ new_order_id, product_type, UINT32_MAX, ORDER_WAIT };
    waiting_orders_.push(new_order_id);
    return new_order_id;
}

bool OrderManager::GetOrderByID(uint32_t order_id, Order& order) const
{
    // Return Read-only order info
    if (const auto it = order_pool_.find(order_id); it != order_pool_.end())
    {
        order = it->second;
        return true;
    }
    return false;
}

size_t OrderManager::GetWaitOrderNum() const
{
    return waiting_orders_.size();
}

bool OrderManager::IsOrderDone(uint32_t order_id)
{
    auto it = order_pool_.find(order_id);
    if (it == order_pool_.end())
    {
        ERROR_MSG("[ORDER] Failed to get order by id");
        return false;
    }
    return it->second.status == ORDER_FINISHED;
}

bool OrderManager::TryAssignNewOrderToTray(uint32_t tray_id, uint32_t& order_id)
{
    if (GetWaitOrderNum() == 0)
    {
        INFO_MSG("[ORDER] No order to be assigned");
        return false;
    }
    order_id = waiting_orders_.front();
    waiting_orders_.pop();
    running_orders_.push_back(order_id);

    auto it = order_pool_.find(order_id);
    if (it == order_pool_.end())
    {
        ERROR_MSG("[ORDER] Failed to get order by id");
        return false;
    }
    it->second.tray_id = tray_id;
    it->second.status = ORDER_EXECUTING;

    INFO_MSG("[ORDER] Order {} assigned to tray {}", order_id, tray_id);

    return true;
}

void OrderManager::OnOrderProcessSuccess(const uint32_t order_id, const ST_ProcessInfo& process)
{
    auto it = order_pool_.find(order_id);
    if (it == order_pool_.end())
    {
        ERROR_MSG("[ORDER] Failed to get order by id");
        return;
    }
    it->second.executed_processes.push_back(process);
}

void OrderManager::UpdateOrderStatus(uint32_t order_id)
{
    // Mark order as finished successfully for now
    const auto it = order_pool_.find(order_id);
    if (it == order_pool_.end())
    {
        ERROR_MSG("[ORDER] UpdateOrderStatus: order {} not found", order_id);
        return;
    }

    // Update status in pool
    it->second.status = ORDER_FINISHED;

    // Move from running to finished lists
    running_orders_.remove(order_id);
    finished_orders_.push_back(order_id);

    INFO_MSG("[ORDER] Order {} marked as FINISHED", order_id);
}
