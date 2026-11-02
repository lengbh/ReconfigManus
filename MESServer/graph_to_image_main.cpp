#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <string>
#include "GraphManager.h"

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
}

int main(int argc, char* argv[])
{
    if (argc < 3 || argc > 5)
    {
        std::cerr << "Usage: GraphRender <graph_json_file> <png|pdf> [-s] [-k|--keep-dot]\n";
        std::cerr << "  -s: symbolic/small render, showing only vertex names and no edge details\n";
        std::cerr << "  -k, --keep-dot: keep the intermediate .dot file (deleted by default)\n";
        return 1;
    }

    const std::string graph_file = argv[1];
    const std::string format = ToLower(argv[2]);
    if (format != "png" && format != "pdf")
    {
        std::cerr << "Unsupported format: " << argv[2] << ". Use png or pdf.\n";
        return 1;
    }

    bool symbolic = false;
    bool keep_dot = false;
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
        else
        {
            std::cerr << "Unsupported flag: " << argv[i]
                      << ". Use -s for symbolic/small render or -k/--keep-dot to keep the .dot file.\n";
            return 1;
        }
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
    const std::filesystem::path base_path = output_dir / input_path.stem();
    const std::filesystem::path dot_path = base_path.string() + ".dot";
    const std::filesystem::path output_path = base_path.string() + "." + format;

    GraphManager graph_manager(j_graph);
    graph_manager.WriteOutDotFile(dot_path.string(), symbolic);

    const std::string command = "dot -T" + format + " " + ShellQuote(dot_path.string()) +
        " -o " + ShellQuote(output_path.string());

    const int status = std::system(command.c_str());
    if (!keep_dot)
    {
        std::error_code ec;
        std::filesystem::remove(dot_path, ec);
        if (ec)
        {
            std::cerr << "Warning: failed to delete intermediate dot file: " << dot_path << "\n";
        }
    }

    if (status != 0)
    {
        std::cerr << "Failed to execute Graphviz command:\n" << command << "\n";
        return 1;
    }

    std::cout << "Generated: " << output_path << "\n";
    return 0;
}
