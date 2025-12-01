//
// Created by bohanleng on 04/11/2025.
//

#include "ProductManager.h"
#include <nlohmann/json.hpp>
#include "LogMacros.h"

using nlohmann::json;

Product::Product(const json& products, uint8_t product_type)
{
    // TODO check validity of the file
    for (const auto & product : products["products"])
    {
        // Only reading one type of product for now
        if (product["product_type"] == product_type)
        {
            product["product_name"].get_to(product_name);
            for (const auto & process : product["processes"])
                processes.push_back(process["process_id"]);
        }
    }
}

bool Product::GetFirstProcess(ST_ProcessInfo& out) const
{
    if (processes.empty())
        return false;
    out = processes.front();
    return true;
}

bool Product::GetRemainingProcesses(const Order& order, std::vector<ST_ProcessInfo>& out) const
{
    out.clear();

    const size_t exec_sz = order.executed_processes.size();

    // Perfect-prefix assumption: all executed steps must equal the first exec_sz steps of processes
    if (exec_sz > processes.size())
    {
        ERROR_MSG("[PRODUCT] Executed steps exceed defined process length.");
        return false;
    }
    for (size_t i = 0; i < exec_sz; ++i)
    {
        if (order.executed_processes[i] != processes[i])
        {
            ERROR_MSG("[PRODUCT] Executed steps do not match product process prefix.");
            return false;
        }
    }

    // If already completed, no remaining
    if (exec_sz == processes.size())
        return false;

    // Push every remaining process from the current position to the end
    for (size_t i = exec_sz; i < processes.size(); ++i)
        out.push_back(processes[i]);
    return !out.empty();
}

bool Product::GetLastProcess(ST_ProcessInfo& out) const
{
    if (processes.empty())
        return false;
    out = processes.back();
    return true;
}
