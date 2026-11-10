#ifndef RECONFIGMANUS_SMPGRAPHRENDERER_H
#define RECONFIGMANUS_SMPGRAPHRENDERER_H

#include <nlohmann/json.hpp>
#include <set>
#include <string>

namespace SMPGraphRenderer
{
// Freeze the original flow layout, then place local state diagrams outside
// its arcs. Export this positioned DOT with neato -n2 to preserve geometry.
void WriteDotFile(const nlohmann::json& graph, const std::string& filename,
                  const std::set<int>& below_stations = {},
                  const std::set<int>& closer_stations = {});
}

#endif // RECONFIGMANUS_SMPGRAPHRENDERER_H
