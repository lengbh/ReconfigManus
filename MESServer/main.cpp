#include <iostream>
#include <fstream>
#include <nlohmann/json.hpp>
#include "MESServer.h"

using json = nlohmann::json;
#define DEFAULT_CONFIG_FILE "mes_server_cfg.json"

int main(int argc, char* argv[]) {
    const char* cfg_file = DEFAULT_CONFIG_FILE;
    if (argc > 1) {
        cfg_file = argv[1];
    }
    uint16_t bind_port;
    std::string system_graph_file;
    std::string system_capabilities_file;
    std::string products_file;
    uint8_t product_type;

    // Load MES server config (bind port)
    json j_cfg;
    try {
        std::ifstream f_cfg(cfg_file);
        j_cfg = json::parse(f_cfg);
        j_cfg["mes_service"]["bind_port"].get_to(bind_port);
        j_cfg["production_system"]["graph_file"].get_to(system_graph_file);
        j_cfg["production_system"]["capabilities_file"].get_to(system_capabilities_file);
        j_cfg["product_info"]["products_file"].get_to(products_file);
        j_cfg["product_info"]["product_type"].get_to(product_type);
    } catch (const std::exception& e) {
        std::cout << "Configuration file parsing failed (" << cfg_file << "):\n" << e.what();
        return 1;
    }

    // Load system graph model JSON
    json j_graph;
    try {
        std::ifstream f_graph(system_graph_file);
        j_graph = json::parse(f_graph);
    } catch (const std::exception& e) {
        std::cout << "Graph model file parsing failed (" << system_graph_file << "):\n" << e.what();
        return 1;
    }

    // Load station capabilities JSON
    json j_capabilities;
    try {
        std::ifstream f_station(system_capabilities_file);
        j_capabilities = json::parse(f_station);
    } catch (const std::exception& e) {
        std::cout << "Station config file parsing failed (" << system_capabilities_file << "):\n" << e.what();
        return 1;
    }

    // 4) Load products JSON
    json j_products;
    try {
        std::ifstream f_products(products_file);
        j_products = json::parse(f_products);
    } catch (const std::exception& e) {
        std::cout << "Products file parsing failed (" << products_file << "):\n" << e.what();
        return 1;
    }

    auto server = std::make_unique<MESServer>(bind_port, j_graph, j_capabilities, j_products, product_type);
    server->CreateOrderBatch(100);

    std::cout << "MES Server started at port: " << bind_port << "\n";
    server->Start();
    server->Run();
}