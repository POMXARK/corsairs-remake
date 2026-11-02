import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// the log of PDM nodes: a read-only text field that is filled after every run
app.registerExtension({
  name: "pdm.parts.log",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData.name.startsWith("PDMPart")) return;
    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (m) {
      onExecuted?.apply(this, arguments);
      let w = this.widgets?.find((x) => x.name === "log");
      if (!w) {
        w = ComfyWidgets["STRING"](this, "log", ["STRING", { multiline: true }], app).widget;
        w.inputEl.readOnly = true;
        w.inputEl.style.opacity = 0.85;
      }
      w.value = (m.text || []).join("\n");
      this.setSize([Math.max(this.size[0], 460), Math.max(this.size[1], 340)]);
      app.graph.setDirtyCanvas(true, true);
    };
  },
});
