// Dumps decompiled C of every function and all defined strings to <outdir>/<program>.c / .strings.txt
// Extra args are hex addresses of functions the analysis missed (reached only through a virtual
// table): they are disassembled and made functions first.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.data.StringDataInstance;
import java.io.*;

public class DumpDecomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = getScriptArgs()[0];
        String name = currentProgram.getName();
        String[] args = getScriptArgs();
        for (int i = 1; i < args.length; i++) {
            var at = toAddr(Long.parseLong(args[i], 16));
            disassemble(at);
            if (getFunctionAt(at) == null) createFunction(at, null);
        }
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(new FileWriter(new File(outDir, name + ".c")))) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                if (monitor.isCancelled()) break;
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                w.println("// " + f.getEntryPoint() + " " + f.getName());
                if (r != null && r.decompileCompleted()) w.println(r.getDecompiledFunction().getC());
                else w.println("// decompile failed");
            }
        }
        try (PrintWriter w = new PrintWriter(new FileWriter(new File(outDir, name + ".strings.txt")))) {
            for (Data d : currentProgram.getListing().getDefinedData(true)) {
                StringDataInstance s = StringDataInstance.getStringDataInstance(d);
                if (s != StringDataInstance.NULL_INSTANCE && s.getStringValue() != null)
                    w.println(d.getAddress() + "\t" + s.getStringValue().replace("\n", "\\n"));
            }
        }
        di.dispose();
    }
}
