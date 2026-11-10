#ifndef RECONFIGMANUS_SMPCONFIG_H
#define RECONFIGMANUS_SMPCONFIG_H

#include <cmath>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <unordered_set>

namespace SMPConfig
{
// MES keeps its nominal service-time estimate; simulation executes failure/repair.
inline const nlohmann::json& ServiceTimeDistribution(const nlohmann::json& vertex)
{
    if (!vertex.contains("smp"))
        return vertex.at("service_time_distribution");

    const auto& model = vertex.at("smp");
    const auto& states = model.at("states");
    if (!states.is_array() || model.at("initial_state") != "idle")
        throw std::invalid_argument("Station SMP must start idle");
    const std::unordered_set<std::string> state_names = states.get<std::unordered_set<std::string>>();
    const bool has_failure = state_names.contains("failed");
    const std::unordered_set<std::string> expected_states = has_failure
        ? std::unordered_set<std::string>{"idle", "running", "failed"}
        : std::unordered_set<std::string>{"idle", "running"};
    if (state_names != expected_states || states.size() != state_names.size())
        throw std::invalid_argument("Station SMP supports idle/running with optional failed repair state");

    const auto& probabilities = model.at("transition_probabilities");
    const auto& distributions = model.at("holding_time_distributions");
    if (!probabilities.is_object() || probabilities.size() != state_names.size()
        || !distributions.is_object() || distributions.size() != state_names.size())
        throw std::invalid_argument("Station SMP requires one probability row per state");
    const std::unordered_set<std::string> types = {
        "constant", "normal", "uniform", "exponential", "triangular", "weibull",
        "empirical", "uniform_mixture",
    };
    for (const auto& state : state_names)
    {
        const auto& row = probabilities.at(state);
        const auto& times = distributions.at(state);
        const std::unordered_set<std::string> expected_targets = state == "running"
            ? (has_failure ? std::unordered_set<std::string>{"idle", "failed"}
                           : std::unordered_set<std::string>{"idle"})
            : std::unordered_set<std::string>{"running"};
        if (!row.is_object() || !times.is_object())
            throw std::invalid_argument("Invalid SMP probability row");
        double sum = 0.0;
        std::unordered_set<std::string> targets;
        for (auto it = row.begin(); it != row.end(); ++it)
        {
            const double probability = it.value().get<double>();
            if (!state_names.contains(it.key()) || !std::isfinite(probability) || probability < 0.0)
                throw std::invalid_argument("Invalid SMP transition probability");
            sum += probability;
            if (probability == 0.0)
                continue;
            targets.insert(it.key());
            const auto& distribution = times.at(it.key());
            if (state == "idle")
            {
                if (!distribution.is_null())
                    throw std::invalid_argument("Idle SMP holding time must be externally controlled (null)");
                continue;
            }
            if (!distribution.is_object())
                throw std::invalid_argument("Running and failed SMP states require timed transitions");
            const auto type = distribution.at("type").get<std::string>();
            const auto& parameters = distribution.at("parameters");
            const std::size_t expected_size = type == "uniform_mixture" ? 5 : type == "triangular" ? 3
                : (type == "constant" || type == "exponential" ? 1 : 2);
            if (!types.contains(type) || !parameters.is_array()
                || (type == "empirical" ? parameters.empty() : parameters.size() != expected_size))
                throw std::invalid_argument("Invalid SMP holding-time distribution");
            for (const auto& value : parameters)
                if (!value.is_number() || !std::isfinite(value.get<double>()))
                    throw std::invalid_argument("SMP distribution parameters must be finite numbers");
            if (type == "empirical")
                for (const auto& value : parameters)
                    if (value.get<double>() < 0)
                        throw std::invalid_argument("Empirical holding times must be nonnegative");
            if (type == "uniform_mixture"
                && !(parameters[0].get<double>() >= 0 && parameters[0].get<double>() <= 1
                    && parameters[1].get<double>() >= 0 && parameters[1] <= parameters[2]
                    && parameters[3].get<double>() >= 0 && parameters[3] <= parameters[4]))
                throw std::invalid_argument("Invalid uniform mixture weight or interval bounds");
        }
        if (std::abs(sum - 1.0) > 1e-12)
            throw std::invalid_argument("SMP transition probabilities must sum to 1");
        if (targets != expected_targets || times.size() != targets.size())
            throw std::invalid_argument("Unsupported station SMP transitions");
    }

    const auto& running = distributions.at("running").at("idle");
    if (vertex.contains("service_time_distribution") && vertex.at("service_time_distribution") != running)
        throw std::invalid_argument("Conflicting SMP and legacy service-time distributions");
    return running;
}
}

#endif // RECONFIGMANUS_SMPCONFIG_H
