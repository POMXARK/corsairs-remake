// The window "Market": the tables of the markets (program/market.c) in the running game. It reads and
// changes the script arrays at once (the next price of trade.c takes them), shows what each market
// sells and buys for now, and writes the tables back into market.c. The #define numbers are compiled
// into the script, so the window only previews them; they work after a save and a restart.

#include "core.h"
#include "storm/editor/engine_editor.hpp"
#include "storm/editor/storm_imgui.hpp"
#include "v_data.h"

#include <fmt/format.h>

#include <algorithm>
#include <array>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>

namespace corsairs::editor
{
namespace
{

using storm::editor::EngineEditor;

constexpr int kGoods = 4;
constexpr int kMarkets = 3;
// the engine runs from game/, where the scripts are
constexpr const char *kMarketC = "program/market.c";
constexpr const char *kGoodNames[kGoods] = {"sugar", "rum", "cloth", "powder"};
constexpr const char *kMarketNames[kMarkets] = {"Gull Island", "Crag", "Palm Key"};
// portIsland of trade.c
constexpr const char *kIslands[kMarkets] = {"gull", "crag", "palm"};

// the #define numbers of market.c, by the names of the file
struct Defines
{
    std::array<const char *, 4> names{"MARKET_RECOVERY", "MARKET_PRICE_MIN", "MARKET_PRICE_MAX", "MARKET_BUYS"};
    std::array<int, 4> values{20, 50, 150, 95};
    bool read = false;

    int &min() { return values[1]; }
    int &max() { return values[2]; }
    int &buys() { return values[3]; }
};

std::string ReadText(const char *path)
{
    std::ifstream file(path, std::ios::binary);
    std::stringstream text;
    text << file.rdbuf();
    return text.str();
}

Defines ReadDefines()
{
    Defines defines;
    const std::string text = ReadText(kMarketC);
    defines.read = !text.empty();
    for (size_t i = 0; i < defines.names.size(); ++i)
    {
        std::smatch m;
        if (std::regex_search(text, m, std::regex(fmt::format(R"(#define\s+{}\s+(-?\d+))", defines.names[i]))))
        {
            defines.values[i] = std::stoi(m[1]);
        }
        else
        {
            defines.read = false;
        }
    }
    return defines;
}

VDATA *Var(const char *name)
{
    return static_cast<VDATA *>(core.GetScriptVariable(name));
}

// an element of an array, or the variable itself (an index on a single one is an error of the script)
int Get(VDATA *v, int index)
{
    int32_t value = 0;
    if (v->IsArray())
    {
        v->Get(value, index);
    }
    else
    {
        v->Get(value);
    }
    return value;
}

// Trade_SellPrice of trade.c, with the integer arithmetic of the script
int SellPrice(int base, int price, int norm, int stock, Defines &d)
{
    int percent = 200 - stock * 100 / std::max(norm, 1);
    percent = std::clamp(percent, d.min(), std::max(d.min(), d.max()));
    return std::max(base * price / 100 * percent / 100, 1);
}

int BuyPrice(int sell, Defines &d)
{
    return std::max(sell * d.buys() / 100, 1);
}

// "{\n\t160, 110, 65, 80,\n\t...}": a market a line, as economy/market_c.py writes it
std::string Rows(VDATA *v)
{
    std::string rows = "{";
    for (int m = 0; m < kMarkets; ++m)
    {
        rows += m == 0 ? "\n\t" : ",\n\t";
        for (int g = 0; g < kGoods; ++g)
        {
            rows += (g == 0 ? "" : ", ") + std::to_string(Get(v, m * kGoods + g));
        }
    }
    return rows + "}";
}

// Puts the tables and the numbers into market.c, leaving the rest of the file as it is
bool Save(VDATA *base, VDATA *price, VDATA *norm, Defines &d)
{
    std::string text = ReadText(kMarketC);
    if (text.empty())
    {
        return false;
    }
    text = std::regex_replace(text, std::regex(R"(int goodBase\[4\] = \{[^}]*\})"),
                              fmt::format("int goodBase[4] = {{{}, {}, {}, {}}}", Get(base, 0), Get(base, 1),
                                          Get(base, 2), Get(base, 3)));
    text = std::regex_replace(text, std::regex(R"(int marketPrice\[12\] = \{[^}]*\})"),
                              "int marketPrice[12] = " + Rows(price));
    text = std::regex_replace(text, std::regex(R"(int marketNorm\[12\] = \{[^}]*\})"),
                              "int marketNorm[12] = " + Rows(norm));
    for (size_t i = 0; i < d.names.size(); ++i)
    {
        text = std::regex_replace(text, std::regex(fmt::format(R"(#define {} -?\d+)", d.names[i])),
                                  fmt::format("#define {} {}", d.names[i], d.values[i]));
    }
    // the note of who wrote the tables last, the one economy/market_c.py writes too
    text = std::regex_replace(text, std::regex(R"(// Written by [^\n]*\n\n?)"), "");
    const auto goods = text.find("\n// the goods:");
    if (goods != std::string::npos)
    {
        text.insert(goods + 1, "// Written by the editor, the window Market: the tables as set in the game.\n\n");
    }
    std::ofstream(kMarketC, std::ios::binary) << text;
    return true;
}

// an integer cell of the table; returns the new value into the script array
void Cell(const char *id, VDATA *v, int index, int step)
{
    int value = Get(v, index);
    ImGui::SetNextItemWidth(-FLT_MIN);
    if (ImGui::DragInt(id, &value, static_cast<float>(step), 0, 100000))
    {
        v->Set(static_cast<int32_t>(value), index);
    }
}

void ShowMarket(bool &active)
{
    static Defines defines;
    static std::string status;
    static bool loaded = false;
    if (!loaded)
    {
        defines = ReadDefines();
        loaded = true;
    }

    if (!ImGui::Begin("Market", &active))
    {
        ImGui::End();
        return;
    }
    VDATA *base = Var("goodBase");
    VDATA *price = Var("marketPrice");
    VDATA *norm = Var("marketNorm");
    VDATA *stock = Var("marketStock");
    if (base == nullptr || price == nullptr || norm == nullptr || stock == nullptr)
    {
        ImGui::TextDisabled("No market.c and trade.c in the running script");
        ImGui::End();
        return;
    }

    // the player: where he is and what he has
    VDATA *island = Var("portIsland");
    const char *here = island != nullptr ? island->GetString() : nullptr;
    if (VDATA *gold = Var("gold"))
    {
        ImGui::Text("Gold %d", Get(gold, 0));
        ImGui::SameLine();
    }
    if (VDATA *cargo = Var("cargo"))
    {
        std::string hold = "Hold:";
        for (int g = 0; g < kGoods; ++g)
        {
            hold += fmt::format(" {} {}", kGoodNames[g], Get(cargo, g));
        }
        ImGui::TextUnformatted(hold.c_str());
    }

    ImGui::SeparatorText("Base price, pesos");
    if (ImGui::BeginTable("base", kGoods, ImGuiTableFlags_SizingStretchSame))
    {
        for (int g = 0; g < kGoods; ++g)
        {
            ImGui::TableNextColumn();
            ImGui::TextUnformatted(kGoodNames[g]);
            Cell(fmt::format("##base{}", g).c_str(), base, g, 1);
        }
        ImGui::EndTable();
    }

    for (int m = 0; m < kMarkets; ++m)
    {
        const bool port = here != nullptr && std::string(here) == kIslands[m];
        ImGui::SeparatorText(port ? fmt::format("{} (the brig is here)", kMarketNames[m]).c_str() : kMarketNames[m]);
        ImGui::PushID(m);
        constexpr ImGuiTableFlags flags = ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_SizingStretchSame;
        if (ImGui::BeginTable("market", 6, flags))
        {
            for (const char *column : {"good", "price %", "norm", "stock", "sells", "buys"})
            {
                ImGui::TableSetupColumn(column);
            }
            ImGui::TableHeadersRow();
            for (int g = 0; g < kGoods; ++g)
            {
                const int i = m * kGoods + g;
                ImGui::PushID(g);
                ImGui::TableNextColumn();
                ImGui::TextUnformatted(kGoodNames[g]);
                ImGui::TableNextColumn();
                Cell("##price", price, i, 5);
                ImGui::SetItemTooltip("Percent of the base: what the island makes is cheap, what it lacks dear");
                ImGui::TableNextColumn();
                Cell("##norm", norm, i, 5);
                ImGui::SetItemTooltip("The stock at which the market sells at its price");
                ImGui::TableNextColumn();
                Cell("##stock", stock, i, 1);
                ImGui::SetItemTooltip("The stock now; days of the map bring it back to the norm");
                const int sell = SellPrice(Get(base, g), Get(price, i), Get(norm, i), Get(stock, i), defines);
                ImGui::TableNextColumn();
                ImGui::Text("%d", sell);
                ImGui::TableNextColumn();
                ImGui::Text("%d", BuyPrice(sell, defines));
                ImGui::PopID();
            }
            ImGui::EndTable();
        }
        ImGui::PopID();
    }

    ImGui::SeparatorText("market.c");
    ImGui::DragInt("Recovery, % a day", &defines.values[0], 1, 0, 100);
    ImGui::DragInt("Price min, %", &defines.min(), 1, 1, 1000);
    ImGui::DragInt("Price max, %", &defines.max(), 1, 1, 1000);
    ImGui::DragInt("Market buys at, %", &defines.buys(), 1, 1, 1000);
    ImGui::TextDisabled("These numbers are compiled in: the prices above preview them, the game takes them after a restart");
    if (ImGui::Button("Save to market.c"))
    {
        status = Save(base, price, norm, defines) ? fmt::format("Written {}", kMarketC)
                                                   : fmt::format("Cannot read {}", kMarketC);
        core.Trace("EDITOR: %s", status.c_str());
    }
    ImGui::SetItemTooltip("The base, the price and the norm tables and the numbers; the stock is of the game, not of the file");
    ImGui::SameLine();
    if (ImGui::Button("Reload numbers"))
    {
        defines = ReadDefines();
    }
    if (!status.empty())
    {
        ImGui::SameLine();
        ImGui::TextUnformatted(status.c_str());
    }
    ImGui::End();
}

// the module registers its window when it is linked into the engine
[[maybe_unused]] const bool registered = [] {
    EngineEditor::RegisterEditorTool("Market", ShowMarket);
    return true;
}();

} // namespace
} // namespace corsairs::editor
