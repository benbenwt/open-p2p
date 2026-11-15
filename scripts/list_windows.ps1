Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;

public class WinEnum {
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
    delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] static extern int GetWindowTextLengthW(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);

    public static List<string> List() {
        var r = new List<string>();
        EnumWindows((h, l) => {
            if (!IsWindowVisible(h)) return true;
            int len = GetWindowTextLengthW(h);
            if (len == 0) return true;
            var sb = new StringBuilder(len + 1);
            GetWindowTextW(h, sb, sb.Capacity);
            uint pid; GetWindowThreadProcessId(h, out pid);
            r.Add(h.ToInt64() + "\t" + pid + "\t" + sb.ToString());
            return true;
        }, IntPtr.Zero);
        return r;
    }
}
"@

Write-Output "=== visible windows (hwnd | pid | title) ==="
[WinEnum]::List() | ForEach-Object { $_ }