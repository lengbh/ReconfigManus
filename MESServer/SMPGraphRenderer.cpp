#include "SMPGraphRenderer.h"
#include "GraphManager.h"
#include "SMPConfig.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iterator>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace
{
using nlohmann::json;

struct TemporaryLayout
{
    std::filesystem::path directory;
    TemporaryLayout()
    {
        const auto timestamp = std::chrono::steady_clock::now().time_since_epoch().count();
        directory = std::filesystem::temp_directory_path() / ("graphrender-smp-" + std::to_string(timestamp));
        if (!std::filesystem::create_directory(directory))
            throw std::runtime_error("Cannot create temporary SMP layout directory");
    }
    ~TemporaryLayout()
    {
        std::error_code error;
        std::filesystem::remove_all(directory, error);
    }
};

std::string ShellQuote(const std::string& value)
{
    std::string result = "'";
    for (const char character : value)
        result += character == '\'' ? "'\\''" : std::string(1, character);
    return result + '\'';
}

std::string Quote(const std::string& value)
{
    std::string result = "\"";
    for (const char character : value)
    {
        switch (character)
        {
            case '\\': result += "\\\\"; break;
            case '"': result += "\\\""; break;
            case '\n': result += "\\n"; break;
            case '\r': break;
            case '\t': result += "\\t"; break;
            default: result += character;
        }
    }
    return result + '"';
}

struct Point
{
    double x, y;
};

Point ReadPoint(const std::string& text)
{
    Point point{};
    char comma = 0;
    std::istringstream input(text);
    if (!(input >> point.x >> comma >> point.y) || comma != ',')
        throw std::runtime_error("Invalid Graphviz position: " + text);
    return point;
}

std::string Position(Point point)
{
    std::ostringstream output;
    output << std::fixed << std::setprecision(5) << point.x << ',' << point.y;
    return output.str();
}

std::string StraightLine(Point start, Point end)
{
    std::string path;
    for (int index = 0; index < 4; ++index)
    {
        if (index)
            path += ' ';
        const double fraction = index / 3.0;
        path += Position({start.x + fraction * (end.x - start.x),
                          start.y + fraction * (end.y - start.y)});
    }
    return path;
}

constexpr double StateRadius = 0.38 * 72 / 2;
constexpr double StateSpacing = 64;

std::string StateCurve(Point from, Point to)
{
    const double direction = to.x > from.x ? 1 : -1;
    const double bend = -direction;
    const double angle = std::acos(-1.0) / 9; // Twenty-degree contacts on the state circles.
    const double contact_x = StateRadius * std::cos(angle);
    const double contact_y = StateRadius * std::sin(angle);
    const double spacing = std::abs(to.x - from.x);
    const Point start{from.x + direction * contact_x, from.y + bend * contact_y};
    const Point tip{to.x - direction * contact_x, to.y + bend * contact_y};
    const Point first{from.x + direction * spacing * 0.33, from.y + bend * StateRadius * 0.95};
    const Point second{to.x - direction * spacing * 0.33, to.y + bend * StateRadius * 0.95};
    const Point end{tip.x - direction * 4, tip.y};
    return "e," + Position(tip) + ' ' + Position(start) + ' ' + Position(first)
        + ' ' + Position(second) + ' ' + Position(end);
}

json StationModel(const json& vertex)
{
    const auto& service = SMPConfig::ServiceTimeDistribution(vertex);
    if (vertex.contains("smp"))
        return vertex.at("smp");
    return {
        {"initial_state", "idle"},
        {"states", {"idle", "running"}},
        {"transition_probabilities", {{"idle", {{"running", 1.0}}}, {"running", {{"idle", 1.0}}}}},
        {"holding_time_distributions", {{"idle", {{"running", nullptr}}}, {"running", {{"idle", service}}}}},
    };
}

std::string StateId(int station, const std::string& state)
{
    return "S" + std::to_string(station) + '_' + state;
}

void AppendStation(std::ostream& output, const json& vertex, std::size_t graph_index,
                   const json& machine, double side_x, double side_y, bool below, bool closer)
{
    const int id = vertex.at("id");
    const auto model = StationModel(vertex);
    const auto& states = model.at("states");
    const std::string initial_state = model.at("initial_state");
    const Point center = ReadPoint(machine.at("pos"));
    const double width = std::stod(machine.at("width").get<std::string>()) * 72;
    const double height = std::stod(machine.at("height").get<std::string>()) * 72;
    const double state_y = below ? center.y - height / 2 - 42 : side_y;
    double first_x = below ? center.x - StateSpacing * (states.size() - 1) / 2 : side_x;
    if (closer)
    {
        const double attachment_length = side_x - StateRadius - (center.x + width / 2);
        first_x -= attachment_length / 2;
    }
    std::map<std::string, Point> positions;
    // The base DOT already holds the workstation's original position and style.
    output << "  " << graph_index << " [smp_machine_id=" << id << "];\n";
    std::size_t index = 0;
    for (const auto& value : states)
    {
        const std::string state = value;
        const std::string symbol = state == "idle" ? "I" : state == "running" ? "R" : "F";
        const Point position{first_x + StateSpacing * index++, state_y};
        positions[state] = position;
        output << "  " << Quote(StateId(id, state)) << " [label=" << Quote(symbol)
               << ", smp_station=" << id << ", smp_state=" << Quote(state)
               << ", smp_initial=" << (state == initial_state ? "true" : "false")
               << ", shape=circle, width=0.38, height=0.38, fixedsize=true, pos=" << Quote(Position(position))
               << ", fontname=\"Times-Roman\", fontsize=11, style=filled, fillcolor=white, "
               << "color=" << Quote(state == "failed" ? "#b62929" : "black") << "];\n";
    }

    Point attachment, start;
    std::string destination;
    if (below)
    {
        // Attach to the middle of the local diagram, just above its state row.
        attachment = {center.x, state_y + 22};
        start = {center.x, center.y - height / 2};
        destination = "anchor_S" + std::to_string(id);
        output << "  " << Quote(destination)
               << " [shape=point, label=\"\", style=invis, width=0.01, height=0.01, pos="
               << Quote(Position(attachment)) << ", smp_station=" << id << "];\n";
    }
    else
    {
        attachment = positions.at(initial_state);
        attachment.x -= StateRadius;
        start = {center.x + width / 2, center.y};
        destination = StateId(id, initial_state);
    }
    output << "  " << graph_index << " -> " << Quote(destination)
           << " [smp_association=true, smp_placement=" << (below ? "below" : "right")
           << ", style=dotted, dir=none, color=gray55, penwidth=0.8, pos="
           << Quote(StraightLine(start, attachment)) << "];\n";

    for (const auto& from_value : states)
    {
        const std::string from = from_value;
        const auto& row = model.at("transition_probabilities").at(from);
        for (auto entry = row.begin(); entry != row.end(); ++entry)
        {
            const double probability = entry.value();
            if (probability <= 0)
                continue;
            const auto& distribution = model.at("holding_time_distributions").at(from).at(entry.key());
            const bool failure_edge = from == "failed" || entry.key() == "failed";
            output << "  " << Quote(StateId(id, from)) << " -> " << Quote(StateId(id, entry.key()))
                   << " [label=\"\", arrowsize=0.55, penwidth=0.8, "
                   << "smp_probability=" << std::setprecision(17) << probability
                   << ", smp_holding=" << Quote(distribution.dump())
                   << ", color=" << Quote(failure_edge ? "#b62929" : "black")
                   << ", pos=" << Quote(StateCurve(positions.at(from), positions.at(entry.key()))) << "];\n";
        }
    }
}
}

void SMPGraphRenderer::WriteDotFile(const nlohmann::json& graph, const std::string& filename,
                                  const std::set<int>& below_stations, const std::set<int>& closer_stations)
{
    std::set<int> placed_stations = below_stations;
    placed_stations.insert(closer_stations.begin(), closer_stations.end());
    for (const int station : placed_stations)
    {
        if (below_stations.contains(station) && closer_stations.contains(station))
            throw std::invalid_argument("Choose either bottom or closer side placement for station " + std::to_string(station));
        bool found = false;
        for (const auto& vertex : graph.at("vertices"))
            found = found || vertex.at("id").get<int>() == station;
        if (!found)
            throw std::invalid_argument("Unknown station for SMP placement: " + std::to_string(station));
    }
    for (const auto& vertex : graph.at("vertices"))
        StationModel(vertex);

    TemporaryLayout layout;
    const auto base_file = layout.directory / "material_flow.dot";
    const auto positioned_file = layout.directory / "positioned.dot";
    const auto reference_file = layout.directory / "reference.json";
    GraphManager(graph).WriteOutDotFile(base_file.string());
    // Lay out the unannotated production graph once. Both exports share this
    // same layout; adding an SMP must never move a machine or reroute an arc.
    const std::string command = "dot -Tdot -o " + ShellQuote(positioned_file.string())
        + " -Tjson -o " + ShellQuote(reference_file.string()) + ' ' + ShellQuote(base_file.string());
    if (std::system(command.c_str()) != 0)
        throw std::runtime_error("Cannot lay out the original material-flow graph");

    std::ifstream reference_stream(reference_file);
    const auto reference = json::parse(reference_stream);
    std::map<std::string, const json*> machines;
    for (const auto& node : reference.at("objects"))
        machines[node.at("name").get<std::string>()] = &node;
    std::string bounds = reference.at("bb");
    std::replace(bounds.begin(), bounds.end(), ',', ' ');
    double left, bottom, right, top;
    std::istringstream bounds_input(bounds);
    if (!(bounds_input >> left >> bottom >> right >> top))
        throw std::runtime_error("Invalid Graphviz material-flow bounds");

    std::ifstream positioned_stream(positioned_file);
    const std::string positioned((std::istreambuf_iterator<char>(positioned_stream)), std::istreambuf_iterator<char>());
    const auto closing_brace = positioned.find_last_of('}');
    if (closing_brace == std::string::npos)
        throw std::runtime_error("Original material-flow diagram is incomplete");

    std::ofstream output(filename);
    if (!output)
        throw std::runtime_error("Cannot write SMP diagram: " + filename);
    output << positioned.substr(0, closing_brace)
           << "  graph [notranslate=true, overlap=true, splines=true, "
           << "label=\"I: idle    R: running    F: failed\", labelloc=b, fontsize=11];\n";
    std::size_t index = 0;
    std::vector<double> occupied_rows;
    for (const auto& vertex : graph.at("vertices"))
    {
        const auto& machine = *machines.at(std::to_string(index));
        const bool below = below_stations.contains(vertex.at("id").get<int>());
        double row_y = ReadPoint(machine.at("pos")).y;
        if (!below)
        {
            // If machines share a flow rank, stack their outside annotations
            // instead of letting their state circles occupy the same points.
            const double clearance = 2 * StateRadius + 14;
            while (std::any_of(occupied_rows.begin(), occupied_rows.end(),
                              [row_y, clearance](double y) { return std::abs(row_y - y) < clearance; }))
                row_y -= clearance;
            occupied_rows.push_back(row_y);
        }
        AppendStation(output, vertex, index++, machine, right + 42, row_y, below,
                      closer_stations.contains(vertex.at("id").get<int>()));
    }
    output << "}\n";
    output.close();
    if (!output)
        throw std::runtime_error("Failed to write SMP diagram: " + filename);
}
