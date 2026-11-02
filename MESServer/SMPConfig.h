#ifndef RECONFIGMANUS_SMPCONFIG_H
#define RECONFIGMANUS_SMPCONFIG_H

#include <cmath>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <unordered_set>

namespace SMPConfig
{
// MES reads the effective running-time distribution; the simulator executes the SMP.
inline const nlohmann::json& ServiceTimeDistribution(const nlohmann::json& vertex)
{
    if (!vertex.contains("smp"))
        return vertex.at("service_time_distribution");

    const auto& model = vertex.at("smp");
    const auto& states = model.at("states");
    if (!states.is_array() || states.size() != 2 || model.at("initial_state") != "idle")
        throw std::invalid_argument("Station SMP must start idle and contain idle/running states");
    const std::unordered_set<std::string> state_names = states.get<std::unordered_set<std::string>>();
    if (state_names != std::unordered_set<std::string>{"idle", "running"})
        throw std::invalid_argument("Only ideal idle/running station SMPs are supported");

    const auto& probabilities = model.at("transition_probabilities");
    if (!probabilities.is_object() || probabilities.size() != 2)
        throw std::invalid_argument("Station SMP requires one probability row per state");
    for (const auto& state : {"idle", "running"})
    {
        const auto& row = probabilities.at(state);
        const std::string expected_target = std::string(state) == "idle" ? "running" : "idle";
        if (!row.is_object())
            throw std::invalid_argument("Invalid SMP probability row");
        double sum = 0.0;
        for (auto it = row.begin(); it != row.end(); ++it)
        {
            const double probability = it.value().get<double>();
            if (!state_names.contains(it.key()) || !std::isfinite(probability) || probability < 0.0
                || (probability > 0.0 && it.key() != expected_target))
                throw std::invalid_argument("Station SMP transitions must alternate idle and running");
            sum += probability;
        }
        if (std::abs(sum - 1.0) > 1e-12)
            throw std::invalid_argument("SMP transition probabilities must sum to 1");
    }

    const auto& distributions = model.at("holding_time_distributions");
    if (!distributions.is_object() || distributions.size() != 2
        || !distributions.at("idle").is_object() || distributions.at("idle").size() != 1
        || !distributions.at("running").is_object() || distributions.at("running").size() != 1
        || !distributions.at("idle").at("running").is_null())
        throw std::invalid_argument("Idle SMP holding time must be externally controlled (null)");

    const auto& running = distributions.at("running").at("idle");
    const auto type = running.at("type").get<std::string>();
    const auto& parameters = running.at("parameters");
    const std::unordered_set<std::string> types = {
        "constant", "normal", "uniform", "exponential", "triangular", "weibull",
    };
    if (!types.contains(type) || !parameters.is_array())
        throw std::invalid_argument("Invalid SMP running-time distribution");
    const std::size_t expected_size = type == "triangular" ? 3
        : (type == "constant" || type == "exponential" ? 1 : 2);
    if (parameters.size() != expected_size)
        throw std::invalid_argument("Invalid SMP running-time distribution parameters");
    if (vertex.contains("service_time_distribution") && vertex.at("service_time_distribution") != running)
        throw std::invalid_argument("Conflicting SMP and legacy service-time distributions");
    return running;
}
}

#endif // RECONFIGMANUS_SMPCONFIG_H
