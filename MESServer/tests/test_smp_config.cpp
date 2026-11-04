#include "SMPConfig.h"
#include <fstream>
#include <iostream>

using nlohmann::json;

void Require(bool condition, const std::string& message)
{
    if (!condition)
        throw std::runtime_error(message);
}

void ExpectRejected(const json& vertex)
{
    try
    {
        SMPConfig::ServiceTimeDistribution(vertex);
    }
    catch (const std::exception&)
    {
        return;
    }
    throw std::runtime_error("Invalid station SMP was accepted");
}

int main(int argc, char* argv[])
{
    try
    {
        Require(argc == 2, "Expected graph fixture path");
        std::ifstream input(argv[1]);
        const auto graph = json::parse(input);
        json repairable;
        for (const auto& vertex : graph.at("vertices"))
        {
            const auto& expected = vertex.at("smp").at("holding_time_distributions").at("running").at("idle");
            Require(SMPConfig::ServiceTimeDistribution(vertex) == expected, "Nominal service distribution changed");
            json legacy = vertex;
            legacy.erase("smp");
            legacy["service_time_distribution"] = expected;
            Require(SMPConfig::ServiceTimeDistribution(legacy) == expected, "Legacy loading changed");
            if (vertex.at("id") == 5)
                repairable = vertex;
        }
        Require(repairable.at("smp").at("states").size() == 3, "Workstation 5 must model failure");
        auto invalid = repairable;
        invalid["smp"]["holding_time_distributions"]["failed"]["running"] = nullptr;
        ExpectRejected(invalid);
        invalid = repairable;
        invalid["smp"]["initial_state"] = "running";
        ExpectRejected(invalid);
        invalid = repairable;
        invalid["smp"]["transition_probabilities"]["running"]["idle"] = 0.99;
        ExpectRejected(invalid);
        invalid = repairable;
        invalid["smp"]["transition_probabilities"]["failed"] = {{"idle", 1.0}};
        ExpectRejected(invalid);
        invalid = repairable;
        invalid["service_time_distribution"] = {{"type", "constant"}, {"parameters", {1}}};
        ExpectRejected(invalid);
        std::cout << "Ideal, legacy and repairable station SMP configuration checks passed\n";
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
