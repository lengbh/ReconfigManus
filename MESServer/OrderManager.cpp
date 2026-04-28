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
    return new_order_id;
}

void OrderManager::AddProductionTarget(const uint8_t product_type, const uint32_t count)
{
    if (count == 0)
        return;

    remaining_order_targets_[product_type] += count;
    total_remaining_order_targets_ += count;
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
    return total_remaining_order_targets_;
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

    std::uniform_int_distribution<uint32_t> distribution(1, total_remaining_order_targets_);
    uint32_t pick = distribution(rng_);
    uint8_t selected_product_type = UINT8_MAX;
    for (auto & [product_type, remaining_count] : remaining_order_targets_)
    {
        if (remaining_count == 0)
            continue;

        if (pick <= remaining_count)
        {
            selected_product_type = product_type;
            --remaining_count;
            --total_remaining_order_targets_;
            break;
        }
        pick -= remaining_count;
    }

    if (selected_product_type == UINT8_MAX)
    {
        ERROR_MSG("[ORDER] Failed to select product type for new order");
        return false;
    }

    order_id = CreateNewOrder(selected_product_type);
    running_orders_.push_back(order_id);

    auto it = order_pool_.find(order_id);
    if (it == order_pool_.end())
    {
        ERROR_MSG("[ORDER] Failed to get order by id");
        return false;
    }
    it->second.tray_id = tray_id;
    it->second.status = ORDER_EXECUTING;

    INFO_MSG("[ORDER] Order {} of product type {} assigned to tray {}", order_id, selected_product_type, tray_id);

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
