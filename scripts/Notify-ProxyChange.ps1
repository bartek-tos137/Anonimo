if (-not ('Anonimo.WinInet' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
namespace Anonimo {
    public static class WinInet {
        [DllImport("wininet.dll", SetLastError = true)]
        public static extern bool InternetSetOption(IntPtr handle, int option, IntPtr buffer, int length);
    }
}
'@
}
[Anonimo.WinInet]::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null
[Anonimo.WinInet]::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null
