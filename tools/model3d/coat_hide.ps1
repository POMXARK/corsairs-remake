# Start 3DCoat with a script and keep its windows out of the user's way while it runs (coat_run.sh, HIDE=desk|off|min).
#   desk - (default) 3DCoat runs on its own desktop 'coatdesk' (CreateDesktop, STARTUPINFO.lpDesktop): its windows are
#          never on the user's screen and cannot take the focus; it draws frames there and the script runs
#          (solid_auv $RemoveUVIntr 22 s, the same result as with a normal window). Tested 2026-11-04.
# start /min is not enough: 3DCoat restores its main window itself after loading. So every 0.15 s, while the process
# lives, each visible top-level window of the process is
#   off - put off the screen at (-32000, -32000), never activated: it starts minimized, its restored place
#         is set off the screen (SetWindowPlacement) and only then it is shown, so it does not flash; 3DCoat keeps
#         drawing frames there and the script runs (23 s), but 3DCoat activates itself: in the test the foreground
#         went to it at once and SetForegroundWindow could give it back only once, so the user's browser lost focus;
#   min - kept minimized without activation (SW_SHOWMINNOACTIVE). Tested 2026-11-04: a minimized 3DCoat draws no
#         frames and never starts the script (empty coat_log.txt after 75 s), so this mode is only for checks.
# Focus: the user works at this PC (a browser video froze and blurred when 3DCoat took the focus), so the launcher
# itself is started hidden (coat_run.vbs, no console), 3DCoat is created with SW_SHOWMINNOACTIVE (Start-Process
# -WindowStyle Minimized is SW_SHOWMINIMIZED, which activates) and below normal priority, and whenever the
# foreground window belongs to 3DCoat the window that had the focus before the start gets it back (logged 'focus').
# The state of the main window goes to coat_hide.log next to this file (checked by coat_run.sh).
param([string]$Exe, [string]$Script, [string]$Mode = 'desk')
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class CoatWin {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr p);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetWindowPlacement(IntPtr h, ref PLACE p);
  [DllImport("user32.dll")] public static extern bool SetWindowPlacement(IntPtr h, ref PLACE p);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool on);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] public struct SI {
    public int cb; public string r, desk, title; public int x, y, w, h, cx, cy, fill, flags; public short show, r2;
    public IntPtr r3, i, o, e; }
  [StructLayout(LayoutKind.Sequential)] public struct PI { public IntPtr hp, ht; public int pid, tid; }
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] public static extern bool CreateProcess(string app, string cmd,
    IntPtr pa, IntPtr ta, bool inh, uint fl, IntPtr env, string dir, ref SI si, out PI pi);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr CreateDesktop(string name, IntPtr d, IntPtr m,
    uint fl, uint acc, IntPtr sa);
  public static int Start(string exe, string args, string desk) {
    SI si = new SI(); si.cb = Marshal.SizeOf(si); si.flags = 1; si.show = 7; si.desk = desk;  // STARTF_USESHOWWINDOW, SW_SHOWMINNOACTIVE
    PI pi;
    if (!CreateProcess(exe, "\"" + exe + "\" " + args, IntPtr.Zero, IntPtr.Zero, false, 0x4000, IntPtr.Zero, null, ref si, out pi))
      return -1;  // 0x4000 BELOW_NORMAL_PRIORITY_CLASS
    return pi.pid;
  }
  public static bool GiveBack(IntPtr prev) {  // attach to the thread of the current foreground window to be allowed to switch
    uint q; uint t = GetWindowThreadProcessId(GetForegroundWindow(), out q), me = GetCurrentThreadId();
    AttachThreadInput(me, t, true); bool ok = SetForegroundWindow(prev); AttachThreadInput(me, t, false); return ok;
  }
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct PLACE { public int len, flags, show; public int mx, my, xx, xy; public RECT r; }
}
'@
$log = Join-Path $PSScriptRoot 'coat_hide.log'
"start $Mode $(Get-Date -Format o)" | Set-Content $log
$fg0 = [CoatWin]::GetForegroundWindow()
$desk = $null
if ($Mode -eq 'desk') {
  if ([CoatWin]::CreateDesktop('coatdesk', [IntPtr]::Zero, [IntPtr]::Zero, 0, 0x10000000, [IntPtr]::Zero) -eq [IntPtr]::Zero) {
    "CreateDesktop failed" | Add-Content $log; exit 1 }
  $desk = 'WinSta0\coatdesk'
}
$id = [CoatWin]::Start($Exe, "-script `"$Script`"", $desk)
if ($id -lt 0) { "CreateProcess failed" | Add-Content $log; exit 1 }
$p = Get-Process -Id $id
$n = 0
while (-not $p.HasExited) {
  $wins = New-Object System.Collections.ArrayList
  $cb = [CoatWin+EnumProc] { param($h, $x) $q = 0; [void][CoatWin]::GetWindowThreadProcessId($h, [ref]$q)
    if ($q -eq $p.Id -and [CoatWin]::IsWindowVisible($h)) { [void]$wins.Add($h) }; $true }
  [void][CoatWin]::EnumWindows($cb, [IntPtr]::Zero)
  foreach ($h in $wins) {
    if ($Mode -eq 'desk') { break }
    if ($Mode -eq 'off') {
      $r = New-Object CoatWin+RECT; [void][CoatWin]::GetWindowRect($h, [ref]$r)
      if ([CoatWin]::IsIconic($h)) {
        $pl = New-Object CoatWin+PLACE; $pl.len = [Runtime.InteropServices.Marshal]::SizeOf($pl)
        [void][CoatWin]::GetWindowPlacement($h, [ref]$pl)
        $w = $pl.r.R - $pl.r.L; $ht = $pl.r.B - $pl.r.T
        $pl.r.L = -32000; $pl.r.T = -32000; $pl.r.R = -32000 + $w; $pl.r.B = -32000 + $ht
        $pl.show = 4  # SW_SHOWNOACTIVATE: restored straight to the off-screen place
        [void][CoatWin]::SetWindowPlacement($h, [ref]$pl)
        [void][CoatWin]::GetWindowRect($h, [ref]$r)
      }
      if ($r.L -gt -30000) { [void][CoatWin]::SetWindowPos($h, [IntPtr]::Zero, -32000, -32000, 0, 0, 0x0015) }  # NOSIZE|NOZORDER|NOACTIVATE
    } elseif (-not [CoatWin]::IsIconic($h)) {
      [void][CoatWin]::ShowWindow($h, 7)  # SW_SHOWMINNOACTIVE
    }
  }
  $fg = [CoatWin]::GetForegroundWindow(); $q = 0; [void][CoatWin]::GetWindowThreadProcessId($fg, [ref]$q)
  if ($q -eq $p.Id -and $fg0 -ne [IntPtr]::Zero) { "focus taken at t $n, given back $([CoatWin]::GiveBack($fg0))" | Add-Content $log }
  if (($n++ % 20) -eq 0 -and $wins.Count) {
    $h = $wins[0]; $r = New-Object CoatWin+RECT; [void][CoatWin]::GetWindowRect($h, [ref]$r)
    "t $n windows $($wins.Count) iconic $([CoatWin]::IsIconic($h)) rect $($r.L) $($r.T) $($r.R) $($r.B)" | Add-Content $log
  }
  Start-Sleep -Milliseconds 150
}
"exit $(Get-Date -Format o)" | Add-Content $log
