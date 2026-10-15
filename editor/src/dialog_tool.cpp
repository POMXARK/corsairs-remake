// The window "Dialog": the dialog of the port as a graph read from the scripts (dialog_graph.hpp):
// the nodes, what each says and where its answers lead, the links to no node and the nodes nothing
// leads to. The node on the screen is marked, "Show in game" opens the dialog on a node (port.c,
// Dialog_EditorNode), and the texts are edited and written back into the scripts; the game takes
// them after a restart, as the scripts are compiled at the start.

#include "dialog_graph.hpp"

#include "core.h"
#include "storm/editor/engine_editor.hpp"
#include "storm/editor/storm_imgui.hpp"
#include "v_data.h"

#include <fmt/format.h>

#include <algorithm>
#include <map>
#include <string>
#include <vector>

namespace corsairs::editor
{
namespace
{

using storm::editor::EngineEditor;

// the engine runs from game/
const std::vector<std::string> kScripts = {"program/port.c", "program/trade.c"};
const ImVec4 kBroken(1.f, 0.4f, 0.4f, 1.f);
const ImVec4 kUnreached(0.6f, 0.6f, 0.6f, 1.f);
const ImVec4 kCurrent(0.4f, 1.f, 0.4f, 1.f);

struct State
{
    DialogGraph graph;
    std::vector<std::string> unreached;
    // the edited texts by "file:offset"
    std::map<std::string, std::vector<char>> buffers;
    std::string status;
    bool loaded = false;

    void Load()
    {
        graph = ReadDialog(kScripts);
        unreached = graph.Unreached();
        buffers.clear();
        loaded = true;
    }
};

std::string Key(const Literal &l)
{
    return fmt::format("{}:{}", l.file, l.offset);
}

int ScriptInt(const char *name)
{
    int32_t value = 0;
    if (auto *v = static_cast<VDATA *>(core.GetScriptVariable(name)))
    {
        v->Get(value);
    }
    return value;
}

std::string ScriptString(const char *name)
{
    auto *v = static_cast<VDATA *>(core.GetScriptVariable(name));
    const char *s = v != nullptr ? v->GetString() : nullptr;
    return s != nullptr ? s : "";
}

bool Broken(const DialogGraph &graph, const Answer &answer)
{
    return !answer.dynamic && !graph.Leads(answer.go);
}

bool HasBroken(const DialogGraph &graph, const Node &node)
{
    for (const Answer &answer : node.answers)
    {
        if (Broken(graph, answer))
        {
            return true;
        }
    }
    return false;
}

// the literals of a line as fields; an expression shows above them
void EditLine(State &state, const Line &line, const char *id)
{
    if (!line.literal)
    {
        ImGui::PushStyleColor(ImGuiCol_Text, kUnreached);
        ImGui::TextWrapped("%s", line.expression.c_str());
        ImGui::PopStyleColor();
    }
    for (size_t i = 0; i < line.pieces.size(); ++i)
    {
        const Literal &piece = line.pieces[i];
        auto &buffer = state.buffers[Key(piece)];
        if (buffer.empty())
        {
            buffer.assign(piece.text.begin(), piece.text.end());
            buffer.resize(piece.text.size() + 1024, '\0');
        }
        ImGui::SetNextItemWidth(-FLT_MIN);
        ImGui::InputText(fmt::format("##{}{}", id, i).c_str(), buffer.data(), buffer.size());
    }
}

std::vector<TextEdit> Edits(const State &state)
{
    std::vector<TextEdit> edits;
    std::map<std::string, bool> seen;
    auto add = [&](const Line &line) {
        for (const Literal &piece : line.pieces)
        {
            const auto it = state.buffers.find(Key(piece));
            if (it != state.buffers.end() && !seen[it->first] && piece.text != it->second.data())
            {
                seen[it->first] = true;
                edits.push_back({piece, it->second.data()});
            }
        }
    };
    for (const Node &node : state.graph.nodes)
    {
        for (const Line &say : node.says)
        {
            add(say);
        }
        for (const Answer &answer : node.answers)
        {
            add(answer.text);
        }
    }
    return edits;
}

void ShowNode(State &state, const Node &node, bool in_port)
{
    const DialogGraph &graph = state.graph;
    ImGui::Text("%s%s", node.name.c_str(), node.dynamic ? " + n" : "");
    ImGui::SameLine();
    ImGui::TextDisabled("%s:%d", node.file.c_str(), node.line);
    ImGui::BeginDisabled(!in_port);
    if (ImGui::Button("Show in game"))
    {
        // a family "g" + g opens on its first one
        const std::string name = node.dynamic ? node.name + "0" : node.name;
        core.PostEvent("Editor_DialogNode", 1, "s", name.c_str());
    }
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("Opens the dialog on this node in the port; the node runs as in the game");
    if (node.leaves)
    {
        ImGui::SameLine();
        ImGui::TextDisabled("closes the dialog");
    }

    if (!node.says.empty())
    {
        ImGui::SeparatorText("Says");
    }
    for (size_t i = 0; i < node.says.size(); ++i)
    {
        EditLine(state, node.says[i], fmt::format("say{}_", i).c_str());
    }

    if (node.answers.empty())
    {
        return;
    }
    ImGui::SeparatorText("Answers");
    constexpr ImGuiTableFlags flags = ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_Resizable;
    if (ImGui::BeginTable("answers", 3, flags))
    {
        ImGui::TableSetupColumn("text", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableSetupColumn("go", ImGuiTableColumnFlags_WidthFixed, 80.f);
        ImGui::TableSetupColumn("in", ImGuiTableColumnFlags_WidthFixed, 80.f);
        ImGui::TableHeadersRow();
        for (size_t i = 0; i < node.answers.size(); ++i)
        {
            const Answer &answer = node.answers[i];
            ImGui::PushID(static_cast<int>(i));
            ImGui::TableNextColumn();
            EditLine(state, answer.text, "answer");
            ImGui::TableNextColumn();
            const std::string go = answer.dynamic ? answer.go + " + n" : answer.go;
            if (Broken(graph, answer))
            {
                ImGui::TextColored(kBroken, "%s", go.c_str());
                ImGui::SetItemTooltip("No node of this name: the dialog would close");
            }
            else if (ImGui::SmallButton(go.c_str()))
            {
                // the twin "buy2" is the node "buy"
                std::string target = answer.go;
                if (graph.Find(target) == nullptr && target.size() > 1 && target.back() == '2')
                {
                    target.pop_back();
                }
                EngineEditor::SetSetting("Dialog.Node", target);
            }
            ImGui::TableNextColumn();
            ImGui::TextDisabled("%s", answer.via.c_str());
            ImGui::PopID();
        }
        ImGui::EndTable();
    }
}

// what the dialog entity shows now: its text and answers, attributes of the script object Dialog
void ShowScreen()
{
    auto *dialog = static_cast<VDATA *>(core.GetScriptVariable("Dialog"));
    ATTRIBUTES *root = dialog != nullptr ? dialog->GetAClass() : nullptr;
    if (root == nullptr)
    {
        return;
    }
    if (ATTRIBUTES *text = root->GetAttributeClass("Text"))
    {
        ImGui::TextWrapped("%s", text->GetValue().c_str());
    }
    if (ATTRIBUTES *links = root->GetAttributeClass("Links"))
    {
        for (size_t i = 0; i < links->GetAttributesNum(); ++i)
        {
            ATTRIBUTES *link = links->GetAttributeClass(static_cast<uint32_t>(i));
            ATTRIBUTES *go = link->GetAttributeClass("go");
            ImGui::BulletText("%s  -> %s", link->GetValue().c_str(), go != nullptr ? go->GetValue().c_str() : "?");
        }
    }
}

void ShowDialog(bool &active)
{
    static State state;
    if (!state.loaded)
    {
        state.Load();
    }
    if (!ImGui::Begin("Dialog", &active))
    {
        ImGui::End();
        return;
    }
    if (!state.graph.error.empty())
    {
        ImGui::TextDisabled("%s", state.graph.error.c_str());
        if (ImGui::Button("Reload"))
        {
            state.Load();
        }
        ImGui::End();
        return;
    }

    const bool in_port = ScriptInt("inPort") != 0;
    const bool open = ScriptInt("dialogOpen") != 0;
    const std::string current = open ? ScriptString("dialogNode") : std::string();

    // the problems of the graph
    int broken = 0;
    for (const Node &node : state.graph.nodes)
    {
        broken += HasBroken(state.graph, node) ? 1 : 0;
    }
    ImGui::Text("%zu nodes", state.graph.nodes.size());
    ImGui::SameLine();
    if (broken > 0)
    {
        ImGui::TextColored(kBroken, "%d with an answer to no node", broken);
    }
    else
    {
        ImGui::TextDisabled("links fine");
    }
    if (!state.unreached.empty())
    {
        std::string list;
        for (const std::string &name : state.unreached)
        {
            list += " " + name;
        }
        ImGui::SameLine();
        ImGui::TextColored(kUnreached, "unreached:%s", list.c_str());
    }
    ImGui::SameLine();
    ImGui::TextDisabled(in_port ? (open ? "| on screen: %s" : "| in the port") : "| not in the port", current.c_str());

    const std::vector<TextEdit> edits = Edits(state);
    ImGui::BeginDisabled(edits.empty());
    if (ImGui::Button(fmt::format("Save texts ({})", edits.size()).c_str()))
    {
        const int written = WriteTexts(edits);
        state.status = written < 0 ? "The scripts changed on disk: reloaded, nothing written"
                                   : fmt::format("Written {} texts; the game takes them after a restart", written);
        core.Trace("EDITOR: dialog %s", state.status.c_str());
        state.Load();
    }
    ImGui::EndDisabled();
    ImGui::SameLine();
    if (ImGui::Button("Reload scripts"))
    {
        state.Load();
        state.status.clear();
    }
    if (!state.status.empty())
    {
        ImGui::SameLine();
        ImGui::TextUnformatted(state.status.c_str());
    }

    std::string selected = EngineEditor::GetSetting("Dialog.Node");
    if (state.graph.Find(selected) == nullptr)
    {
        selected = state.graph.nodes.front().name;
    }

    // the nodes on the left, the picked one on the right
    if (ImGui::BeginChild("nodes", ImVec2(150.f, 0.f), ImGuiChildFlags_Border | ImGuiChildFlags_ResizeX))
    {
        for (const Node &node : state.graph.nodes)
        {
            const bool here = node.name == current ||
                              (node.dynamic && current.rfind(node.name, 0) == 0 && current.size() > node.name.size());
            bool colored = true;
            if (HasBroken(state.graph, node))
            {
                ImGui::PushStyleColor(ImGuiCol_Text, kBroken);
            }
            else if (here)
            {
                ImGui::PushStyleColor(ImGuiCol_Text, kCurrent);
            }
            else if (std::find(state.unreached.begin(), state.unreached.end(), node.name) != state.unreached.end())
            {
                ImGui::PushStyleColor(ImGuiCol_Text, kUnreached);
            }
            else
            {
                colored = false;
            }
            const bool first = std::find(state.graph.first.begin(), state.graph.first.end(), node.name) !=
                               state.graph.first.end();
            const std::string label = fmt::format("{}{}{}{}", here ? "> " : "", node.name, node.dynamic ? " + n" : "",
                                                  first ? "  (opens)" : "");
            if (ImGui::Selectable(label.c_str(), node.name == selected))
            {
                EngineEditor::SetSetting("Dialog.Node", node.name);
            }
            if (colored)
            {
                ImGui::PopStyleColor();
            }
        }
    }
    ImGui::EndChild();
    ImGui::SameLine();
    if (ImGui::BeginChild("node"))
    {
        if (const Node *node = state.graph.Find(selected))
        {
            ShowNode(state, *node, in_port);
        }
        if (open)
        {
            ImGui::SeparatorText("On screen");
            ShowScreen();
        }
    }
    ImGui::EndChild();
    ImGui::End();
}

// the module registers its window when it is linked into the engine
[[maybe_unused]] const bool registered = [] {
    EngineEditor::RegisterEditorTool("Dialog", ShowDialog);
    return true;
}();

} // namespace
} // namespace corsairs::editor
