// The dialog of the port as a graph, read from the scripts: the nodes are the branches
// `if (node == "name")` of Dialog_Node (port.c) and Trade_Node (trade.c), their lines are the calls
// of Say and Answer in the branch and in the functions it calls (Shop_Show, Trade_Good, ...). The
// dialog is code, not data, so this is a reading of it: a text or a "go" made by an expression shows
// as that expression.

#pragma once

#include <map>
#include <string>
#include <vector>

namespace corsairs::editor
{

// a string literal of a script: where its text is, to write it back
struct Literal
{
    std::string file;
    size_t offset = 0; // of the text, after the opening quote
    size_t length = 0;
    std::string text;
};

// the text of Say or of an answer: a literal, or an expression ("Ну что, капитан? В кошельке " + gold)
struct Line
{
    std::string expression;
    // the expression is one literal
    bool literal = false;
    // the literals of the expression, in order: the parts of the text that can be edited
    std::vector<Literal> pieces;
};

struct Answer
{
    Line text;
    // the node it leads to; for "g" + g it is "g" and dynamic
    std::string go;
    bool dynamic = false;
    // the function it is written in, when not in the branch itself
    std::string via;
};

struct Node
{
    std::string name;
    // "g" + g: a family of nodes g0, g1, ...
    bool dynamic = false;
    std::string file;
    int line = 0;
    std::vector<Line> says;
    std::vector<Answer> answers;
    // the branch closes the dialog (Dialog_Leave)
    bool leaves = false;
};

struct DialogGraph
{
    std::vector<Node> nodes;
    // the nodes Dialog_FirstNode can open with
    std::vector<std::string> first;
    std::string error;

    const Node *Find(const std::string &name) const;
    // a node of that name, "g2" matches the family "g"; a twin "buy2" of Answer matches "buy"
    bool Leads(const std::string &go) const;
    // the nodes no answer leads to and the dialog does not open with
    std::vector<std::string> Unreached() const;
};

// reads the scripts, by their paths from the working directory
DialogGraph ReadDialog(const std::vector<std::string> &files);

// a literal and its new text
struct TextEdit
{
    Literal source;
    std::string text;
};

// puts the new texts into their files; a quote of a text becomes an apostrophe (the scripts have
// no escapes). Returns the number of the texts written, -1 when a file changed since it was read.
int WriteTexts(const std::vector<TextEdit> &edits);

} // namespace corsairs::editor
