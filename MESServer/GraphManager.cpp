//
// Created by bohanleng on 30/10/2025.
//

#include "GraphManager.h"
#include <fstream>
#include <iomanip>
#include <limits>
#include <algorithm>
#include <unordered_set>
#include <boost/property_map/function_property_map.hpp>
#include <boost/graph/dijkstra_shortest_paths.hpp>
#include <boost/graph/graphviz.hpp>
#include "LogMacros.h"


GraphManager::GraphManager(const json & graph_model)
{
    graph_ = std::make_unique<LabelledDiGraph>();
    // TODO check validity of the file
    for (const auto & v : graph_model["vertices"])
    {
        ST_VertexLabel vertex_label{};
        v["id"].get_to(vertex_label.id);
        v["name"].get_to(vertex_label.name);
        v["buffer_capacity"].get_to(vertex_label.buffer_capacity);
        {
            std::string tstr;
            v["service_time_distribution"]["type"].get_to(tstr);
            vertex_label.service_time_dist.type = TimeDistTypeFromString(tstr);
        }
        v["service_time_distribution"]["parameters"].get_to(vertex_label.service_time_dist.parameters);

        auto vertex_descriptor = boost::add_vertex(vertex_label, *graph_);
        vertex_map_[vertex_label.id] = vertex_descriptor;
    }
    for (const auto & a : graph_model["arcs"])
    {
        ST_ArcLabel arc_label{};
        a["tail"].get_to(arc_label.tail);
        a["head"].get_to(arc_label.head);
        {
            std::string tstr;
            a["transfer_time_distribution"]["type"].get_to(tstr);
            arc_label.transfer_time_dist.type = TimeDistTypeFromString(tstr);
        }
        a["transfer_time_distribution"]["parameters"].get_to(arc_label.transfer_time_dist.parameters);

        auto [edge_descriptor, success] = boost::add_edge(vertex_map_[arc_label.tail],
            vertex_map_[arc_label.head], arc_label, *graph_);
        if (!success)
        {
            std::cout << "Failed to add arc" << std::endl;
            return;
        }
    }
}

bool GraphManager::GetVertexProperties(uint32_t id, ST_VertexLabel& label) const
{
    auto it = vertex_map_.find(id);
    if (it == vertex_map_.end())
        return false;

    label = (*graph_)[it->second];
    return true;
}

bool GraphManager::GetVertexTimeDist(uint32_t id, ST_TimeDist& dist) const
{
    auto it = vertex_map_.find(id);
    if (it == vertex_map_.end())
        return false;

    dist = (*graph_)[it->second].service_time_dist;
    return true;
}

bool GraphManager::SetVertexTimeDist(uint32_t id, const ST_TimeDist& dist)
{
    auto it = vertex_map_.find(id);
    if (it == vertex_map_.end())
        return false;

    (*graph_)[it->second].service_time_dist = dist;
    return true;
}

bool GraphManager::GetArcProperties(uint32_t tail, uint32_t head, ST_ArcLabel& label) const
{
    auto itTail = vertex_map_.find(tail);
    auto itHead = vertex_map_.find(head);
    if (itTail == vertex_map_.end() || itHead == vertex_map_.end())
        return false;

    auto [e, found] = boost::edge(itTail->second, itHead->second, *graph_);
    if (!found)
        return false;

    label = (*graph_)[e];
    return true;
}

bool GraphManager::GetArcTimeDist(uint32_t tail, uint32_t head, ST_TimeDist& dist) const
{
    auto itTail = vertex_map_.find(tail);
    auto itHead = vertex_map_.find(head);
    if (itTail == vertex_map_.end() || itHead == vertex_map_.end())
        return false;

    auto [e, found] = boost::edge(itTail->second, itHead->second, *graph_);
    if (!found)
        return false;

    dist = (*graph_)[e].transfer_time_dist;
    return true;
}

bool GraphManager::SetArcTimeDist(uint32_t tail, uint32_t head, const ST_TimeDist& dist)
{
    auto itTail = vertex_map_.find(tail);
    auto itHead = vertex_map_.find(head);
    if (itTail == vertex_map_.end() || itHead == vertex_map_.end())
        return false;

    auto [e, found] = boost::edge(itTail->second, itHead->second, *graph_);
    if (!found)
        return false;

    (*graph_)[e].transfer_time_dist = dist;
    return true;
}

bool GraphManager::GetOutgoingNeighborVertices(uint32_t vertex_id, std::list<uint32_t>& out_vertices) const
{
    out_vertices.clear();
    auto it = vertex_map_.find(vertex_id);
    if (it == vertex_map_.end() || !graph_)
        return false;

    using Graph = LabelledDiGraph;
    using vertex_descriptor = boost::graph_traits<Graph>::vertex_descriptor;

    const vertex_descriptor v = it->second;

    // Collect only outgoing neighbors
    auto adj_pair = boost::adjacent_vertices(v, *graph_);
    for (auto ai = adj_pair.first; ai != adj_pair.second; ++ai)
    {
        out_vertices.push_back((*graph_)[*ai].id);
    }

    return !out_vertices.empty();
}

bool GraphManager::GetIncomingNeighborVertices(uint32_t vertex_id, std::list<uint32_t>& out_vertices) const
{
    out_vertices.clear();
    auto it = vertex_map_.find(vertex_id);
    if (it == vertex_map_.end() || !graph_)
        return false;

    using Graph = LabelledDiGraph;
    using vertex_descriptor = boost::graph_traits<Graph>::vertex_descriptor;

    const vertex_descriptor v = it->second;

    // Collect only incoming neighbors
    auto inv_adj_pair = boost::inv_adjacent_vertices(v, *graph_);
    for (auto ai = inv_adj_pair.first; ai != inv_adj_pair.second; ++ai)
        out_vertices.push_back((*graph_)[*ai].id);

    return !out_vertices.empty();
}

void GraphManager::AddArcTimeDistWithVertexTimeDist(uint32_t tail, uint32_t head, uint32_t vertex_id, bool add_or_minus)
{
    if (!graph_) return;

    // Validate vertices exist
    auto itTail = vertex_map_.find(tail);
    auto itHead = vertex_map_.find(head);
    auto itVtx  = vertex_map_.find(vertex_id);
    if (itTail == vertex_map_.end() || itHead == vertex_map_.end() || itVtx == vertex_map_.end())
    {
        ERROR_MSG("[GRAPH] Finding vertices failed");
        return;
    }

    // Validate arc exists
    auto [e, found] = boost::edge(itTail->second, itHead->second, *graph_);
    if (!found)
    {
        ERROR_MSG("[GRAPH] Finding arc failed");
        return;
    }

    // TODO for now assume all normal distribution
    const auto & arc_dist = (*graph_)[e].transfer_time_dist;
    const auto & vtx_dist = (*graph_)[itVtx->second].service_time_dist;
    if (arc_dist.type != TimeDistType::normal || vtx_dist.type != TimeDistType::normal)
    {
        ERROR_MSG("[GRAPH] Not normal distribution, setting Arc time dist failed");
        return;
    }
    
    ST_TimeDist new_dist;
    new_dist.type = TimeDistType::normal;
    new_dist.parameters.emplace_back(arc_dist.parameters[0] + (add_or_minus ? 1 : -1) * vtx_dist.parameters[0]);
    new_dist.parameters.emplace_back(sqrt(arc_dist.parameters[1] * arc_dist.parameters[1]
        + (add_or_minus ? 1 : -1) * vtx_dist.parameters[1] * vtx_dist.parameters[1]));
    
    (*graph_)[e].transfer_time_dist = std::move(new_dist);
}

void GraphManager::AddTimeDistToAllPathsToVertex(uint32_t vertex_id, bool add_or_minus)
{
    if (!graph_) return;

    // Validate vertex exists
    auto it = vertex_map_.find(vertex_id);
    if (it == vertex_map_.end())
        return;

    std::list<uint32_t> incoming_vertices;
    if (!GetIncomingNeighborVertices(vertex_id, incoming_vertices))
    {
        ERROR_MSG("[GRAPH] No incoming neighbor vertices");
        return;
    }

    for (const auto & in_vtx : incoming_vertices)
        AddArcTimeDistWithVertexTimeDist(in_vtx, vertex_id, vertex_id, add_or_minus);

}

bool GraphManager::FindShortestPath(uint32_t tail, uint32_t head, std::vector<uint32_t>& out_path, float& out_length) const
{
    // If head == tail, out_path contains only the same vertex, out_length is 0.0f
    auto itTail = vertex_map_.find(tail);
    auto itHead = vertex_map_.find(head);
    if (itTail == vertex_map_.end() || itHead == vertex_map_.end())
        return false;

    using Graph = LabelledDiGraph;
    using vertex_descriptor = boost::graph_traits<Graph>::vertex_descriptor;
    using edge_descriptor = boost::graph_traits<Graph>::edge_descriptor;

    const auto n = boost::num_vertices(*graph_);
    if (n == 0)
        return false;

    const auto weight_map = boost::make_function_property_map<edge_descriptor, double>(
        [this](const edge_descriptor& e) -> double {
            const auto & transfer_dist = (*graph_)[e].transfer_time_dist;
            return transfer_dist.expected_value();
        }
    );

    std::vector<vertex_descriptor> pred(n);
    std::vector<double> dist(n, std::numeric_limits<double>::infinity());

    auto index_map = get(boost::vertex_index, *graph_);

    // Run Dijkstra from source
    boost::dijkstra_shortest_paths(
        *graph_,
        itTail->second,
        boost::weight_map(weight_map)
            .distance_map(boost::make_iterator_property_map(dist.begin(), index_map))
            .predecessor_map(boost::make_iterator_property_map(pred.begin(), index_map))
    );

    // Return false if unreachable
    if (!std::isfinite(dist[index_map[itHead->second]]))
        return false;

    // Reconstruct the path from head back to tail
    std::vector<uint32_t> rev_path;
    for (auto v = itHead->second; ; )
    {
        rev_path.push_back((*graph_)[v].id);
        if (v == itTail->second) break;
        auto pv = pred[index_map[v]];
        if (pv == v) break; // safety
        v = pv;
    }
    std::ranges::reverse(rev_path);

    out_path = std::move(rev_path);
    out_length = static_cast<float>(dist[index_map[itHead->second]]);
    return true;
}

void GraphManager::WriteOutDotFile(const std::string& filename) const
{
    std::ofstream out(filename);
    if (!out.is_open())
    {
        ERROR_MSG("[GRAPH] Cannot open dot write out file.");
        return;
    }

    using Graph = LabelledDiGraph;
    using VD = boost::graph_traits<Graph>::vertex_descriptor;
    using ED = boost::graph_traits<Graph>::edge_descriptor;

    // TODO rewrite with std::format or format
    struct VertexWriter {
        const Graph* g;
        void operator()(std::ostream& os, const VD& v) const {
            const auto& lbl = (*g)[v];
            const auto& td = lbl.service_time_dist;
            const double mean = lbl.service_time_dist.expected_value();
            os << std::fixed << std::setprecision(1);
            os << " [shape=box, style=filled, fillcolor=lightyellow, color=black, penwidth=1, label=\"" << 'S' << lbl.id;
            if (!lbl.name.empty()) os << ": " << lbl.name;
            os << "\\nmax capacity: " << static_cast<int>(lbl.buffer_capacity)
               << "\\ns" << lbl.id << ": " << TimeDistTypeToString(td.type) << " (";
            for (size_t i = 0; i < td.parameters.size(); ++i) {
                if (i) os << ", ";
                os << td.parameters[i];
            }
            os << ")\"]";
        }
    };

    struct EdgeWriter {
        const Graph* g;
        void operator()(std::ostream& os, const ED& e) const {
            const auto& el = (*g)[e];
            const auto& td = el.transfer_time_dist;
            os << std::fixed << std::setprecision(1);
            os << " [color=black, penwidth=1, arrowsize=1.0, label=\" t" << el.tail << ',' << el.head << ": ";
            os << TimeDistTypeToString(td.type) << " (";
            for (size_t i = 0; i < td.parameters.size(); ++i) {
                if (i) os << ", ";
                os << td.parameters[i];
            }
            os << ")\"]";
        }
    };

    // Can be converted to png using commands:
    // `dot -Tpng xxx.dot -o xxx.png`
    // `dot -Tpdf xxx.dot -o xxx.pdf`
    boost::write_graphviz(out, *graph_, VertexWriter{graph_.get()}, EdgeWriter{graph_.get()});
}


