// The window "Map": the points of the world map as a chart from above. The islands and their waters come
// from the generator of the map (make_worldmap.py of the engine demo worldmap, the game builds its map
// with it), the start of the brig from Map_Home of program/map.c, and while the map is shown the brig,
// the ships after her and the storms come from the WORLDMAP entity. A click moves the brig (the
// attribute playerShipTeleport of the entity), a right click the start, which is written back into
// map.c; the timers of map.c bring «Ворон» and a storm at once.

#include "core.h"
#include "entity.h"
#include "storm/editor/engine_editor.hpp"
#include "storm/editor/storm_imgui.hpp"
#include "v_data.h"

#include <fmt/format.h>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

namespace corsairs::editor
{
namespace
{

using storm::editor::EngineEditor;

// the engine runs from game/; the engine demos are in the submodule next to it
constexpr const char *kMapC = "program/map.c";
constexpr const char *kGenerator = "../engine/demos/worldmap/make_worldmap.py";
// the islands with a port, Market_Island of market.c
constexpr const char *kPorts[] = {"gull", "crag", "palm"};

const ImU32 kSea = IM_COL32(24, 52, 78, 255);
const ImU32 kWaters = IM_COL32(90, 140, 170, 160);
const ImU32 kLand = IM_COL32(150, 125, 80, 255);
const ImU32 kLandHere = IM_COL32(200, 170, 100, 255);
const ImU32 kText = IM_COL32(235, 235, 220, 255);
const ImU32 kBrig = IM_COL32(120, 255, 120, 255);
const ImU32 kStart = IM_COL32(255, 220, 80, 255);
const ImU32 kEnemy = IM_COL32(255, 90, 90, 255);
const ImU32 kStorm = IM_COL32(170, 170, 200, 200);

struct Island
{
    std::string name;
    float x = 0.f, z = 0.f;
    // the mean coast; the waters, where the map says "the waters of ...", reach area times further
    float radius = 0.f;
};

struct Chart
{
    std::vector<Island> islands;
    float world = 2000.f;
    float area = 1.7f;
    // the start of Map_Home, as read and as moved
    float start[2] = {0.f, 0.f};
    bool start_read = false;
    std::string status;
    bool loaded = false;
};

std::string ReadText(const char *path)
{
    std::ifstream file(path, std::ios::binary);
    std::stringstream text;
    text << file.rdbuf();
    return text.str();
}

// ISLANDS = [("gull", -430.0, 320.0, 150.0, 34.0, 1), ...], WORLD and AREA of the generator
void ReadIslands(Chart &chart)
{
    const std::string text = ReadText(kGenerator);
    chart.islands.clear();
    const std::regex island(R"re(\("(\w+)",\s*(-?[\d.]+),\s*(-?[\d.]+),\s*([\d.]+),\s*[\d.]+,\s*\d+\))re");
    for (auto it = std::sregex_iterator(text.begin(), text.end(), island); it != std::sregex_iterator(); ++it)
    {
        chart.islands.push_back({(*it)[1], std::stof((*it)[2]), std::stof((*it)[3]), std::stof((*it)[4])});
    }
    std::smatch m;
    if (std::regex_search(text, m, std::regex(R"(\nWORLD = ([\d.]+))")))
    {
        chart.world = std::stof(m[1]);
    }
    if (std::regex_search(text, m, std::regex(R"(\nAREA = ([\d.]+))")))
    {
        chart.area = std::stof(m[1]);
    }
}

const std::regex kStartX(R"(worldMap\.playerShipX = (-?[\d.]+);)");
const std::regex kStartZ(R"(worldMap\.playerShipZ = (-?[\d.]+);)");

void ReadStart(Chart &chart)
{
    const std::string text = ReadText(kMapC);
    std::smatch x, z;
    chart.start_read = std::regex_search(text, x, kStartX) && std::regex_search(text, z, kStartZ);
    if (chart.start_read)
    {
        chart.start[0] = std::stof(x[1]);
        chart.start[1] = std::stof(z[1]);
    }
}

bool SaveStart(const Chart &chart)
{
    std::string text = ReadText(kMapC);
    if (!std::regex_search(text, kStartX) || !std::regex_search(text, kStartZ))
    {
        return false;
    }
    text = std::regex_replace(text, kStartX, fmt::format("worldMap.playerShipX = {:.1f};", chart.start[0]),
                              std::regex_constants::format_first_only);
    text = std::regex_replace(text, kStartZ, fmt::format("worldMap.playerShipZ = {:.1f};", chart.start[1]),
                              std::regex_constants::format_first_only);
    std::ofstream(kMapC, std::ios::binary) << text;
    return true;
}

VDATA *Var(const char *name)
{
    return static_cast<VDATA *>(core.GetScriptVariable(name));
}

std::string Value(ATTRIBUTES *a, const char *name)
{
    ATTRIBUTES *child = a != nullptr ? a->GetAttributeClass(name) : nullptr;
    return child != nullptr ? child->GetValue() : std::string();
}

// a point of the map
struct Mark
{
    float x = 0.f, z = 0.f, ay = 0.f;
    std::string name;
    float time = 0.f;
};

// The storms and the ships after the brig: the entity gives one at a time, its attribute "cur" set
// to the number fills x, z and the rest (WorldMap::AttributeChanged)
std::vector<Mark> Events(Entity *map, ATTRIBUTES *group, bool ships)
{
    std::vector<Mark> marks;
    if (group == nullptr)
    {
        return marks;
    }
    const auto num = static_cast<int32_t>(group->GetAttributeAsDword("num", 0));
    for (int32_t i = 0; i < num; ++i)
    {
        group->SetAttributeUseDword("cur", i);
        map->AttributeChanged(group->GetAttributeClass("cur"));
        if (static_cast<int32_t>(group->GetAttributeAsDword("cur", -1)) != i)
        {
            break;
        }
        Mark mark;
        mark.x = group->GetAttributeAsFloat("x");
        mark.z = group->GetAttributeAsFloat("z");
        mark.ay = group->GetAttributeAsFloat("ay");
        mark.time = group->GetAttributeAsFloat("time");
        mark.name = ships ? Value(group, "id") : "storm";
        marks.push_back(mark);
    }
    return marks;
}

float ScriptFloat(const char *name)
{
    float value = 0.f;
    if (VDATA *v = Var(name))
    {
        v->Get(value);
    }
    return value;
}

// a timer of map.c: what is left and a button that brings it now
void Timer(const char *label, const char *variable)
{
    VDATA *v = Var(variable);
    if (v == nullptr)
    {
        return;
    }
    ImGui::PushID(variable);
    ImGui::Text("%s in %.0f s", label, ScriptFloat(variable));
    ImGui::SameLine();
    if (ImGui::SmallButton("Now"))
    {
        // the next tick of Map_EncounterCreate (a second) finds it run out
        v->Set(0.f);
    }
    ImGui::PopID();
}

// the brig: a triangle along her heading, the bow at ay (0 north, PI / 2 east)
void Ship(ImDrawList *draw, ImVec2 at, float ay, float size, ImU32 color)
{
    const ImVec2 bow(std::sin(ay), -std::cos(ay));
    const ImVec2 side(-bow.y, bow.x);
    draw->AddTriangleFilled(ImVec2(at.x + bow.x * size, at.y + bow.y * size),
                            ImVec2(at.x - bow.x * size * 0.6f + side.x * size * 0.5f,
                                   at.y - bow.y * size * 0.6f + side.y * size * 0.5f),
                            ImVec2(at.x - bow.x * size * 0.6f - side.x * size * 0.5f,
                                   at.y - bow.y * size * 0.6f - side.y * size * 0.5f),
                            color);
}

void ShowMap(bool &active)
{
    static Chart chart;
    if (!chart.loaded)
    {
        ReadIslands(chart);
        ReadStart(chart);
        chart.loaded = true;
    }
    if (!ImGui::Begin("Map", &active))
    {
        ImGui::End();
        return;
    }

    VDATA *in_map_var = Var("inMap");
    int32_t in_map = 0;
    if (in_map_var != nullptr)
    {
        in_map_var->Get(in_map);
    }
    VDATA *map_var = Var("worldMap");
    ATTRIBUTES *attributes = map_var != nullptr ? map_var->GetAClass() : nullptr;
    Entity *map = in_map != 0 ? core.GetEntityPointer(core.GetEntityId("worldmap")) : nullptr;
    const bool live = map != nullptr && attributes != nullptr;

    Mark brig;
    std::string here;
    std::vector<Mark> ships, storms;
    if (live)
    {
        brig.x = attributes->GetAttributeAsFloat("playerShipX");
        brig.z = attributes->GetAttributeAsFloat("playerShipZ");
        brig.ay = attributes->GetAttributeAsFloat("playerShipAY");
        here = Value(attributes, "island");
        ships = Events(map, attributes->GetAttributeClass("encounter"), true);
        storms = Events(map, attributes->GetAttributeClass("storm"), false);
    }

    if (live)
    {
        ImGui::Text("Brig %.0f, %.0f, heading %.0f°%s", brig.x, brig.z, brig.ay * 180.f / 3.14159265f,
                    here.empty() ? "" : fmt::format(", the waters of {}", here).c_str());
        Timer("Ворон", "ravenTimer");
        ImGui::SameLine(0.f, 20.f);
        Timer("Storm", "stormTimer");
    }
    else
    {
        ImGui::TextDisabled("The map is not shown: the brig, the ships and the storms appear on it");
    }

    // the start of a new game, Map_Home of map.c
    ImGui::BeginDisabled(!chart.start_read);
    ImGui::SetNextItemWidth(160.f);
    ImGui::DragFloat2("Start", chart.start, 1.f, -chart.world / 2.f, chart.world / 2.f, "%.0f");
    ImGui::SetItemTooltip("Where a new game and a sunk brig start, Map_Home of map.c; a right click on the chart sets it");
    ImGui::SameLine();
    if (ImGui::Button("Save to map.c"))
    {
        chart.status = SaveStart(chart) ? fmt::format("Written {}; a new game takes it after a restart", kMapC)
                                        : fmt::format("No Map_Home numbers in {}", kMapC);
        core.Trace("EDITOR: %s", chart.status.c_str());
    }
    ImGui::EndDisabled();
    ImGui::SameLine();
    if (ImGui::Button("Reload"))
    {
        chart.loaded = false;
        chart.status.clear();
    }
    if (!chart.status.empty())
    {
        ImGui::TextUnformatted(chart.status.c_str());
    }
    // without the generator the labels of the islands give their centres (WdmIslands writes them)
    std::vector<Island> islands = chart.islands;
    if (islands.empty() && live)
    {
        if (ATTRIBUTES *labels = attributes->GetAttributeClass("labels"))
        {
            for (size_t i = 0; i < labels->GetAttributesNum(); ++i)
            {
                ATTRIBUTES *label = labels->GetAttributeClass(static_cast<uint32_t>(i));
                if (ATTRIBUTES *position = label->GetAttributeClass("position"))
                {
                    islands.push_back({label->GetThisName(), position->GetAttributeAsFloat("x"),
                                       position->GetAttributeAsFloat("z"), 0.f});
                }
            }
        }
    }
    if (chart.islands.empty())
    {
        ImGui::TextDisabled("No %s: the islands are the points of their labels", kGenerator);
    }

    // the chart: the world square, north up
    const ImVec2 avail = ImGui::GetContentRegionAvail();
    const float side = std::max(100.f, std::min(avail.x, avail.y));
    const ImVec2 origin = ImGui::GetCursorScreenPos();
    ImGui::InvisibleButton("chart", ImVec2(side, side), ImGuiButtonFlags_MouseButtonLeft | ImGuiButtonFlags_MouseButtonRight);
    const float scale = side / chart.world;
    auto screen = [&](float x, float z) {
        return ImVec2(origin.x + (x + chart.world / 2.f) * scale, origin.y + (chart.world / 2.f - z) * scale);
    };
    auto world = [&](ImVec2 p) {
        return ImVec2((p.x - origin.x) / scale - chart.world / 2.f, chart.world / 2.f - (p.y - origin.y) / scale);
    };

    ImDrawList *draw = ImGui::GetWindowDrawList();
    draw->AddRectFilled(origin, ImVec2(origin.x + side, origin.y + side), kSea);
    for (const Island &island : islands)
    {
        const ImVec2 at = screen(island.x, island.z);
        const bool port = std::find_if(std::begin(kPorts), std::end(kPorts),
                                       [&](const char *p) { return island.name == p; }) != std::end(kPorts);
        draw->AddCircle(at, island.radius * chart.area * scale, kWaters, 48);
        draw->AddCircleFilled(at, std::max(island.radius * scale, 4.f), island.name == here ? kLandHere : kLand, 48);
        draw->AddText(ImVec2(at.x - 16.f, at.y - 8.f), kText, (island.name + (port ? " (port)" : "")).c_str());
    }
    const ImVec2 start = screen(chart.start[0], chart.start[1]);
    draw->AddCircle(start, 6.f, kStart, 16, 2.f);
    draw->AddText(ImVec2(start.x + 8.f, start.y - 8.f), kStart, "start");
    for (const Mark &storm : storms)
    {
        const float zone = attributes->GetAttributeAsFloat("stormZone", 90.f);
        draw->AddCircleFilled(screen(storm.x, storm.z), zone * scale, kStorm, 32);
    }
    for (const Mark &ship : ships)
    {
        const ImVec2 at = screen(ship.x, ship.z);
        Ship(draw, at, ship.ay, 7.f, kEnemy);
        draw->AddText(ImVec2(at.x + 8.f, at.y - 8.f), kEnemy, fmt::format("{} {:.0f} s", ship.name, ship.time).c_str());
    }
    if (live)
    {
        Ship(draw, screen(brig.x, brig.z), brig.ay, 9.f, kBrig);
    }

    if (ImGui::IsItemHovered())
    {
        const ImVec2 point = world(ImGui::GetIO().MousePos);
        ImGui::SetTooltip("%.0f, %.0f\n%s", point.x, point.y,
                          live ? "click: the brig sails from here; right click: the start" : "right click: the start");
        if (ImGui::IsMouseClicked(ImGuiMouseButton_Right) && chart.start_read)
        {
            chart.start[0] = std::round(point.x);
            chart.start[1] = std::round(point.y);
        }
        if (ImGui::IsMouseClicked(ImGuiMouseButton_Left) && live)
        {
            // the entity reads the new place when playerShipTeleport is set; on land it finds water
            attributes->SetAttributeUseFloat("playerShipX", point.x);
            attributes->SetAttributeUseFloat("playerShipZ", point.y);
            attributes->SetAttribute("playerShipTeleport", "1");
            map->AttributeChanged(attributes->GetAttributeClass("playerShipTeleport"));
            core.Trace("EDITOR: the brig to %.0f, %.0f", point.x, point.y);
        }
    }
    ImGui::End();
}

// the module registers its window when it is linked into the engine
[[maybe_unused]] const bool registered = [] {
    EngineEditor::RegisterEditorTool("Map", ShowMap);
    return true;
}();

} // namespace
} // namespace corsairs::editor
