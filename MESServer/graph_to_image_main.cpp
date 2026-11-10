#include <algorithm>
#include <cctype>
#include <charconv>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <set>
#include <string>
#include "GraphManager.h"
#include "SMPGraphRenderer.h"

using json = nlohmann::json;

namespace {
std::string ToLower(std::string s)
{
    std::transform(s.begin(), s.end(), s.begin(),
        [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

std::string ShellQuote(const std::string& s)
{
    std::string quoted = "'";
    for (char c : s)
    {
        if (c == '\'')
            quoted += "'\\''";
        else
            quoted += c;
    }
    quoted += "'";
    return quoted;
}

bool ParseStationIds(const std::string& text, std::set<int>& stations)
{
    std::size_t start = 0;
    while (true)
    {
        const auto comma = text.find(',', start);
        const auto end = comma == std::string::npos ? text.size() : comma;
        int station = 0;
        const auto result = std::from_chars(text.data() + start, text.data() + end, station);
        if (result.ec != std::errc{} || result.ptr != text.data() + end || station < 0)
            return false;
        stations.insert(station);
        if (comma == std::string::npos)
            return true;
        start = comma + 1;
    }
}

}

int main(int argc, char* argv[])
{
    if (argc < 3)
    {
        std::cerr << "Usage: GraphRender <graph_json_file> <dot|png|pdf> [-s|--smp] [--smp-below=ID,...] [--smp-closer=ID,...] [-k|--keep-dot]\n";
        std::cerr << "  -s: symbolic/small render, showing only vertex names and no edge details\n";
        std::cerr << "  --smp: preserve the original flow layout and attach state diagrams outside its arcs\n";
        std::cerr << "  --smp-below=ID,...: place selected local state diagrams below their machines\n";
        std::cerr << "  --smp-closer=ID,...: halve selected side attachments, shifting the SMPs toward their machines\n";
        std::cerr << "  -k, --keep-dot: keep the intermediate .dot file (deleted by default)\n";
        return 1;
    }

    const std::string graph_file = argv[1];
    const std::string format = ToLower(argv[2]);
    if (format != "dot" && format != "png" && format != "pdf")
    {
        std::cerr << "Unsupported format: " << argv[2] << ". Use dot, png or pdf.\n";
        return 1;
    }

    bool symbolic = false;
    bool keep_dot = false;
    bool smp = false;
    std::set<int> below_stations;
    std::set<int> closer_stations;
    for (int i = 3; i < argc; ++i)
    {
        const std::string flag = ToLower(argv[i]);
        if (flag == "-s")
        {
            symbolic = true;
        }
        else if (flag == "-k" || flag == "--keep-dot")
        {
            keep_dot = true;
        }
        else if (flag == "--smp")
        {
            smp = true;
        }
        else if (flag.starts_with("--smp-below="))
        {
            if (!ParseStationIds(flag.substr(12), below_stations))
            {
                std::cerr << "--smp-below requires comma-separated nonnegative station IDs.\n";
                return 1;
            }
        }
        else if (flag.starts_with("--smp-closer="))
        {
            if (!ParseStationIds(flag.substr(13), closer_stations))
            {
                std::cerr << "--smp-closer requires comma-separated nonnegative station IDs.\n";
                return 1;
            }
        }
        else
        {
            std::cerr << "Unsupported flag: " << argv[i]
                      << ". Use -s, --smp, --smp-below=ID,..., --smp-closer=ID,... or -k/--keep-dot.\n";
            return 1;
        }
    }
    if (smp && symbolic)
    {
        std::cerr << "Choose either --smp (state models) or -s (symbolic material-flow graph).\n";
        return 1;
    }
    if ((!below_stations.empty() || !closer_stations.empty()) && !smp)
    {
        std::cerr << "--smp-below and --smp-closer require --smp.\n";
        return 1;
    }

    json j_graph;
    try
    {
        std::ifstream f_graph(graph_file);
        if (!f_graph.is_open())
        {
            std::cerr << "Cannot open graph config file: " << graph_file << "\n";
            return 1;
        }
        j_graph = json::parse(f_graph);
    }
    catch (const std::exception& e)
    {
        std::cerr << "Graph config parsing failed (" << graph_file << "):\n" << e.what() << "\n";
        return 1;
    }

    const std::filesystem::path input_path(graph_file);
    const std::filesystem::path output_dir = std::filesystem::current_path();
    const std::filesystem::path base_path = output_dir / (input_path.stem().string() + (smp ? "_states" : ""));
    const std::filesystem::path dot_path = base_path.string() + ".dot";
    const std::filesystem::path output_path = base_path.string() + "." + format;

    try
    {
        if (smp)
            SMPGraphRenderer::WriteDotFile(j_graph, dot_path.string(), below_stations, closer_stations);
        else
        {
            GraphManager graph_manager(j_graph);
            graph_manager.WriteOutDotFile(dot_path.string(), symbolic);
        }
    }
    catch (const std::exception& error)
    {
        std::cerr << "Graph rendering failed: " << error.what() << '\n';
        return 1;
    }
    if (format == "dot")
    {
        std::cout << "Generated: " << dot_path << '\n';
        return 0;
    }

    const std::string command = std::string(smp ? "neato -n2 -T" : "dot -T") + format + " " + ShellQuote(dot_path.string()) +
        " -o " + ShellQuote(output_path.string());

    const int status = std::system(command.c_str());
    if (status != 0)
    {
        std::cerr << "Failed to execute Graphviz command:\n" << command << "\n";
        return 1;
    }
    if (!keep_dot)
    {
        std::error_code ec;
        std::filesystem::remove(dot_path, ec);
        if (ec)
        {
            std::cerr << "Warning: failed to delete intermediate dot file: " << dot_path << "\n";
        }
    }

    std::cout << "Generated: " << output_path << "\n";
    return 0;
}
