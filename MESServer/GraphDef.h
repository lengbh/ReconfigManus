//
// Created by bohanleng on 03/11/2025.
//

#ifndef RECONFIGMANUS_GRAPHDEF_H
#define RECONFIGMANUS_GRAPHDEF_H

#include <string>
#include <vector>
#include <random>


enum TimeDistType
{
    uniform, normal, weibull, exponential, constant, triangular
};

inline TimeDistType TimeDistTypeFromString(const std::string& s) noexcept
{
    if (s == "uniform") return TimeDistType::uniform;
    if (s == "normal") return TimeDistType::normal;
    if (s == "weibull") return TimeDistType::weibull;
    if (s == "exponential") return TimeDistType::exponential;
    if (s == "constant") return TimeDistType::constant;
    if (s == "triangular") return TimeDistType::triangular;
    return TimeDistType::constant;
}

inline const char* TimeDistTypeToString(TimeDistType t) noexcept
{
    switch (t)
    {
        case TimeDistType::uniform: return "uniform";
        case TimeDistType::normal: return "normal";
        case TimeDistType::weibull: return "weibull";
        case TimeDistType::exponential: return "exponential";
        case TimeDistType::constant: return "constant";
        case TimeDistType::triangular: return "triangular";
        default: return "constant";
    }
}

struct ST_TimeDist
{
    TimeDistType type{};
    std::vector<double> parameters;

    [[nodiscard]] double generate_time() const
    {
        static std::random_device rd;
        static std::mt19937 gen(rd()); // seed the generator (static so it's not reseeded every call)

        switch (type)
        {
            case TimeDistType::normal:
            {
                if (parameters.size() >= 2)
                {
                    std::normal_distribution<double> d(parameters[0], parameters[1]);
                    const double x = d(gen);
                    return x > 0 ? x : 0.0;
                }
                return 0.0;
            }
            case TimeDistType::uniform:
            {
                if (parameters.size() >= 2)
                {
                    double a = parameters[0];
                    double b = parameters[1];
                    if (b < a) std::swap(a, b);
                    if (a < b)
                    {
                        std::uniform_real_distribution<double> d(a, b);
                        const double x = d(gen);
                        return x > 0 ? x : 0.0;
                    }
                }
                return 0.0;
            }
            case TimeDistType::exponential:
            {
                if (parameters.size() >= 1)
                {
                    const double lambda = parameters[0];
                    if (lambda > 0)
                    {
                        std::exponential_distribution<double> d(lambda);
                        const double x = d(gen);
                        return x > 0 ? x : 0.0;
                    }
                }
                return 0.0;
            }
            case TimeDistType::constant:
            {
                if (!parameters.empty())
                {
                    const double x = parameters[0];
                    return x > 0 ? x : 0.0;
                }
                return 0.0;
            }
            case TimeDistType::triangular:
            {
                if (parameters.size() >= 3)
                {
                    double a = parameters[0];
                    double b = parameters[1];
                    double c = parameters[2];
                    if (b < a) std::swap(a, b);
                    if (!(a < b)) return 0.0;
                    if (c < a) c = a;
                    if (c > b) c = b;

                    std::uniform_real_distribution<double> U(0.0, 1.0);
                    const double u = U(gen);
                    const double Fc = (c - a) / (b - a);
                    double x;
                    if (u < Fc)
                        x = a + std::sqrt(u * (b - a) * (c - a));
                    else
                        x = b - std::sqrt((1.0 - u) * (b - a) * (b - c));
                    return x > 0 ? x : 0.0;
                }
                return 0.0;
            }
            case TimeDistType::weibull:
            {
                if (parameters.size() >= 2)
                {
                    const double k = parameters[0];
                    const double lambda = parameters[1];
                    if (k > 0 && lambda > 0)
                    {
                        std::weibull_distribution<double> d(k, lambda);
                        const double x = d(gen);
                        return x > 0 ? x : 0.0;
                    }
                }
                return 0.0;
            }
            default:
                return 0.0;
        }
    }

    // for deterministic algorithms
    [[nodiscard]] double expected_value() const noexcept
    {
        switch (type)
        {
            case TimeDistType::normal: // normal(mu, sigma)
                return (parameters.size() >= 2) ? parameters[0] : 0.0;

            case TimeDistType::uniform: // uniform(a, b)
                return (parameters.size() >= 2) ? (parameters[0] + parameters[1]) / 2.0 : 0.0;

            case TimeDistType::exponential: // exponential(lambda) where lambda is rate
                return (!parameters.empty() && parameters[0] > 0) ? (1.0 / parameters[0]) : 0.0;

            case TimeDistType::constant: // constant(value)
                return (!parameters.empty()) ? parameters[0] : 0.0;

            case TimeDistType::triangular: // triangular(a, b, c)
                return (parameters.size() >= 3) ? (parameters[0] + parameters[1] + parameters[2]) / 3.0 : 0.0;

            case TimeDistType::weibull: // weibull(k, lambda)
                if (parameters.size() >= 2 && parameters[0] > 0 && parameters[1] > 0)
                {
                    const double k = parameters[0];
                    const double lambda = parameters[1];
                    return lambda * std::tgamma(1.0 + 1.0 / k);
                }
                return 0.0;

            default:
                return 0.0;
        }
    }

    void change_distribution(TimeDistType inType, const std::vector<double> & inParameters) noexcept
    {
        type = inType;
        parameters = inParameters;
    }

    void change_distribution(const std::vector<double> & inParameters)
    {
        parameters = inParameters;
    }
};


struct ST_VertexLabel
{
    uint32_t id{};
    std::string name;
    uint8_t buffer_capacity;
    ST_TimeDist service_time_dist;
};

struct ST_ArcLabel
{
    uint32_t tail{};
    uint32_t head{};
    ST_TimeDist transfer_time_dist;
    // TODO could add indicator, int queued_number and a std::queue<> containing the timestamp added
};


#endif //RECONFIGMANUS_GRAPHDEF_H