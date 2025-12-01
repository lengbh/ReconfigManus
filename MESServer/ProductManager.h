//
// Created by bohanleng on 04/11/2025.
//

#ifndef RECONFIGMANUS_PRODUCTMANAGER_H
#define RECONFIGMANUS_PRODUCTMANAGER_H

#include <vector>
#include <string>
#include <nlohmann/json.hpp>
#include "mes_server_def.h"
#include "OrderManager.h"

using json = nlohmann::json;

// TODO support mixed-product production
class Product
{
public:
    explicit Product(const json & products, uint8_t product_type);
    ~Product() = default;

    bool GetFirstProcess(ST_ProcessInfo & out) const;
    bool GetRemainingProcesses(const Order & order, std::vector<ST_ProcessInfo> & out) const;
    bool GetLastProcess(ST_ProcessInfo & out) const;

public:
    std::string product_name;
    uint8_t product_type {UINT8_MAX};

    // Assuming linear product process: just a sequence of data steps
    std::vector<ST_ProcessInfo> processes;
};

#endif //RECONFIGMANUS_PRODUCTMANAGER_H