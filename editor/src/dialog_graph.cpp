#include "dialog_graph.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <functional>
#include <regex>
#include <set>
#include <sstream>

namespace corsairs::editor
{
namespace
{

std::string ReadText(const std::string &path)
{
    std::ifstream file(path, std::ios::binary);
    std::stringstream text;
    text << file.rdbuf();
    return text.str();
}

bool IsWord(char c)
{
    return std::isalnum(static_cast<unsigned char>(c)) || c == '_';
}

// past a string literal or a // comment starting at i, or i itself
size_t Skip(const std::string &text, size_t i)
{
    if (text[i] == '"')
    {
        const size_t close = text.find('"', i + 1);
        return close == std::string::npos ? text.size() : close + 1;
    }
    if (text.compare(i, 2, "//") == 0)
    {
        const size_t eol = text.find('\n', i);
        return eol == std::string::npos ? text.size() : eol;
    }
    return i;
}

// the bracket that closes the one at `open` ({ or (), npos when none
size_t Match(const std::string &text, size_t open)
{
    const char in = text[open];
    const char out = in == '{' ? '}' : ')';
    int depth = 0;
    for (size_t i = open; i < text.size();)
    {
        const size_t next = Skip(text, i);
        if (next != i)
        {
            i = next;
            continue;
        }
        if (text[i] == in)
        {
            ++depth;
        }
        else if (text[i] == out && --depth == 0)
        {
            return i;
        }
        ++i;
    }
    return std::string::npos;
}

std::string Trim(const std::string &s)
{
    const size_t b = s.find_first_not_of(" \t\r\n");
    const size_t e = s.find_last_not_of(" \t\r\n");
    return b == std::string::npos ? std::string() : s.substr(b, e - b + 1);
}

struct Arg
{
    std::string expression;
    size_t offset; // of the trimmed expression in the file
};

struct Call
{
    size_t at;
    std::vector<Arg> args;
};

// the calls of `name` in [begin, end) with their arguments, split at the top commas
std::vector<Call> Calls(const std::string &text, size_t begin, size_t end, const std::string &name)
{
    std::vector<Call> calls;
    for (size_t i = begin; i < end;)
    {
        const size_t next = Skip(text, i);
        if (next != i)
        {
            i = next;
            continue;
        }
        if (text.compare(i, name.size(), name) == 0 && (i == 0 || !IsWord(text[i - 1])))
        {
            size_t open = i + name.size();
            while (open < end && text[open] == ' ')
            {
                ++open;
            }
            const size_t close = open < end && text[open] == '(' ? Match(text, open) : std::string::npos;
            if (close != std::string::npos && close < end)
            {
                Call call{i, {}};
                size_t from = open + 1;
                int depth = 0;
                for (size_t k = from; k <= close;)
                {
                    const size_t past = Skip(text, k);
                    if (past != k)
                    {
                        k = past;
                        continue;
                    }
                    if (text[k] == '(')
                    {
                        ++depth;
                    }
                    else if (text[k] == ')' && k != close)
                    {
                        --depth;
                    }
                    if ((text[k] == ',' && depth == 0) || k == close)
                    {
                        const std::string raw = text.substr(from, k - from);
                        const size_t lead = raw.find_first_not_of(" \t\r\n");
                        call.args.push_back({Trim(raw), from + (lead == std::string::npos ? 0 : lead)});
                        from = k + 1;
                    }
                    ++k;
                }
                calls.push_back(std::move(call));
                i = close + 1;
                continue;
            }
        }
        ++i;
    }
    return calls;
}

Line MakeLine(const std::string &file, const Arg &arg)
{
    Line line;
    line.expression = arg.expression;
    const std::string &e = arg.expression;
    for (size_t i = e.find('"'); i != std::string::npos; i = e.find('"', i))
    {
        const size_t close = e.find('"', i + 1);
        if (close == std::string::npos)
        {
            break;
        }
        line.pieces.push_back({file, arg.offset + i + 1, close - i - 1, e.substr(i + 1, close - i - 1)});
        i = close + 1;
    }
    line.literal = line.pieces.size() == 1 && e.front() == '"' && e.back() == '"';
    return line;
}

struct Function
{
    std::string file;
    const std::string *text;
    size_t begin, end; // the body, between its braces
};

// the functions of a script: a line from its first column "type name(", the body in braces
void ReadFunctions(const std::string &file, const std::string &text, std::map<std::string, Function> &functions)
{
    static const std::regex header(R"(^(void|int|string|float|bool)\s+(\w+)\s*\()");
    for (size_t line = 0; line < text.size();)
    {
        size_t eol = text.find('\n', line);
        if (eol == std::string::npos)
        {
            eol = text.size();
        }
        std::smatch m;
        const std::string head = text.substr(line, eol - line);
        if (std::regex_search(head, m, header))
        {
            const size_t open = text.find('{', line);
            const size_t semicolon = text.find(';', line);
            if (open != std::string::npos && (semicolon == std::string::npos || open < semicolon))
            {
                const size_t close = Match(text, open);
                if (close != std::string::npos)
                {
                    functions[m[2]] = {file, &text, open + 1, close};
                    eol = text.find('\n', close);
                    if (eol == std::string::npos)
                    {
                        eol = text.size();
                    }
                }
            }
        }
        line = eol + 1;
    }
}

int LineOf(const std::string &text, size_t at)
{
    return 1 + static_cast<int>(std::count(text.begin(), text.begin() + at, '\n'));
}

class Reader
{
  public:
    explicit Reader(const std::map<std::string, Function> &functions) : functions_(functions)
    {
    }

    // the says, the answers and the leaving of [begin, end) and of the functions it calls
    void Collect(const Function &f, size_t begin, size_t end, Node &node, const std::string &via,
                 std::set<std::string> &visited)
    {
        const std::string &text = *f.text;
        for (const Call &say : Calls(text, begin, end, "Say"))
        {
            if (!say.args.empty())
            {
                node.says.push_back(MakeLine(f.file, say.args[0]));
            }
        }
        for (const Call &call : Calls(text, begin, end, "Answer"))
        {
            if (call.args.size() < 3)
            {
                continue;
            }
            Answer answer;
            answer.text = MakeLine(f.file, call.args[1]);
            answer.via = via;
            const std::string &go = call.args[2].expression;
            std::smatch m;
            static const std::regex literal(R"re(^"(\w*)"$)re");
            static const std::regex prefix(R"re(^"(\w*)"\s*\+)re");
            if (std::regex_match(go, m, literal))
            {
                answer.go = m[1];
            }
            else if (std::regex_search(go, m, prefix))
            {
                answer.go = m[1];
                answer.dynamic = true;
            }
            else
            {
                answer.go = go;
                answer.dynamic = true;
            }
            node.answers.push_back(std::move(answer));
        }
        if (!Calls(text, begin, end, "Dialog_Leave").empty())
        {
            node.leaves = true;
        }
        // the functions it calls that say or answer something
        for (const auto &[name, callee] : functions_)
        {
            if (name == "Say" || name == "Answer" || name == "Dialog_Node" || name == "Trade_Node" ||
                visited.count(name) != 0 || Calls(text, begin, end, name).empty())
            {
                continue;
            }
            visited.insert(name);
            Collect(callee, callee.begin, callee.end, node, name, visited);
        }
    }

    // the branches `if (node == ...)` of a function of nodes
    void Branches(const Function &f, DialogGraph &graph)
    {
        const std::string &text = *f.text;
        static const std::regex name(R"re(node\s*==\s*"(\w*)"(\s*\+)?)re");
        for (size_t i = f.begin; i < f.end;)
        {
            const size_t at = text.find("if (node", i);
            if (at == std::string::npos || at >= f.end)
            {
                break;
            }
            const size_t open = text.find('(', at);
            const size_t close = Match(text, open);
            const std::string condition = text.substr(open, close - open);
            std::vector<std::pair<std::string, bool>> names;
            for (std::sregex_iterator m(condition.begin(), condition.end(), name), last; m != last; ++m)
            {
                names.emplace_back((*m)[1], (*m)[2].matched);
            }
            // the body: a block, or one statement
            size_t body = close + 1;
            while (body < f.end && std::isspace(static_cast<unsigned char>(text[body])))
            {
                ++body;
            }
            size_t end = text[body] == '{' ? Match(text, body) : text.find(';', body);
            if (end == std::string::npos || end > f.end)
            {
                end = f.end;
            }
            // one node for the branch; "buy2" is the twin Answer makes of "buy", "g" + g + "2" of "g" + g
            if (!names.empty())
            {
                Node node;
                node.name = names.front().first;
                node.dynamic = names.front().second;
                node.file = f.file;
                node.line = LineOf(text, at);
                std::set<std::string> visited;
                Collect(f, body, end, node, "", visited);
                if (graph.Find(node.name) == nullptr)
                {
                    graph.nodes.push_back(std::move(node));
                }
            }
            i = end;
        }
    }

  private:
    const std::map<std::string, Function> &functions_;
};

} // namespace

const Node *DialogGraph::Find(const std::string &name) const
{
    for (const Node &node : nodes)
    {
        if (node.name == name)
        {
            return &node;
        }
    }
    return nullptr;
}

bool DialogGraph::Leads(const std::string &go) const
{
    if (Find(go) != nullptr)
    {
        return true;
    }
    for (const Node &node : nodes)
    {
        // "g2" of the family "g" + g
        if (node.dynamic && go.size() > node.name.size() && go.compare(0, node.name.size(), node.name) == 0 &&
            std::all_of(go.begin() + node.name.size(), go.end(), [](char c) { return std::isdigit(c); }))
        {
            return true;
        }
    }
    return go.size() > 1 && go.back() == '2' && Find(go.substr(0, go.size() - 1)) != nullptr;
}

std::vector<std::string> DialogGraph::Unreached() const
{
    std::set<std::string> reached(first.begin(), first.end());
    for (const Node &node : nodes)
    {
        for (const Answer &answer : node.answers)
        {
            reached.insert(answer.go);
        }
    }
    std::vector<std::string> unreached;
    for (const Node &node : nodes)
    {
        if (reached.count(node.name) == 0)
        {
            unreached.push_back(node.name);
        }
    }
    return unreached;
}

DialogGraph ReadDialog(const std::vector<std::string> &files)
{
    DialogGraph graph;
    // the texts stay alive while the functions point into them
    static std::map<std::string, std::string> texts;
    texts.clear();
    std::map<std::string, Function> functions;
    for (const std::string &file : files)
    {
        std::string &text = texts[file] = ReadText(file);
        if (text.empty())
        {
            graph.error = "Cannot read " + file;
            return graph;
        }
        ReadFunctions(file, text, functions);
    }
    Reader reader(functions);
    for (const char *name : {"Dialog_Node", "Trade_Node"})
    {
        if (const auto it = functions.find(name); it != functions.end())
        {
            reader.Branches(it->second, graph);
        }
    }
    if (const auto it = functions.find("Dialog_FirstNode"); it != functions.end())
    {
        const Function &f = it->second;
        const std::string body = f.text->substr(f.begin, f.end - f.begin);
        static const std::regex returns(R"re(return\s+"(\w+)")re");
        for (std::sregex_iterator m(body.begin(), body.end(), returns), last; m != last; ++m)
        {
            graph.first.push_back((*m)[1]);
        }
    }
    if (graph.nodes.empty())
    {
        graph.error = "No Dialog_Node in the scripts";
    }
    return graph;
}

int WriteTexts(const std::vector<TextEdit> &edits)
{
    std::map<std::string, std::vector<const TextEdit *>> by_file;
    for (const TextEdit &edit : edits)
    {
        by_file[edit.source.file].push_back(&edit);
    }
    int written = 0;
    for (auto &[file, list] : by_file)
    {
        std::string text = ReadText(file);
        // from the end, so the offsets before stay right
        std::sort(list.begin(), list.end(),
                  [](const TextEdit *a, const TextEdit *b) { return a->source.offset > b->source.offset; });
        for (const TextEdit *edit : list)
        {
            const Literal &s = edit->source;
            if (s.offset + s.length > text.size() || text.compare(s.offset, s.length, s.text) != 0)
            {
                return -1;
            }
            std::string value = edit->text;
            std::replace(value.begin(), value.end(), '"', '\'');
            std::replace(value.begin(), value.end(), '\n', ' ');
            text.replace(s.offset, s.length, value);
            ++written;
        }
        std::ofstream(file, std::ios::binary) << text;
    }
    return written;
}

} // namespace corsairs::editor
