#include "SMPConfig.h"
#include "GraphDef.h"
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
        auto flexible = repairable;
        flexible["smp"]["holding_time_distributions"]["failed"]["running"] = {
            {"type", "uniform_mixture"}, {"parameters", {0.8, 10, 20, 100, 120}}};
        SMPConfig::ServiceTimeDistribution(flexible);
        flexible["smp"]["holding_time_distributions"]["running"]["idle"] = {
            {"type", "empirical"}, {"parameters", {1, 1, 1, 10}}};
        SMPConfig::ServiceTimeDistribution(flexible);
        auto empirical = ST_TimeDist{TimeDistTypeFromString("empirical"), {1, 1, 1, 10}};
        Require(std::abs(empirical.expected_value() - 3.25) < 1e-12, "Incorrect empirical mean");
        auto mixture = ST_TimeDist{TimeDistTypeFromString("uniform_mixture"), {0.8, 10, 20, 100, 120}};
        Require(std::abs(mixture.expected_value() - 34.0) < 1e-12, "Incorrect mixture mean");
        for (int i = 0; i < 100; ++i)
        {
            const double value = mixture.generate_time();
            Require((value >= 10 && value <= 20) || (value >= 100 && value <= 120), "Mixture sampled its gap");
            const double observation = empirical.generate_time();
            Require(observation == 1 || observation == 10, "Empirical sampled unobserved time");
        }
        invalid = flexible;
        invalid["smp"]["holding_time_distributions"]["failed"]["running"]["parameters"][0] = 1.1;
        ExpectRejected(invalid);
        invalid = flexible;
        invalid["smp"]["holding_time_distributions"]["running"]["idle"]["parameters"] = json::array();
        ExpectRejected(invalid);
        std::cout << "Ideal, legacy and repairable station SMP configuration checks passed\n";
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
