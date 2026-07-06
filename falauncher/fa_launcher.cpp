// ============================================================================
//  FA Secure Launcher  (C++ / embedded WebBrowser control)
// ----------------------------------------------------------------------------
//  A single Win32 window hosting the built-in IE/MSHTML WebBrowser ActiveX
//  control (shdocvw / IWebBrowser2). Faithful port of fa_launcher.py:
//
//    1. Read settings from launcher.ini (server login URL, game dir, ...).
//    2. Show the server login page inside an embedded browser form.
//    3. When the page navigates to the ticket download (/download, which the
//       server serves as ticket_<pid>.vr1), cancel the browser's own download
//       and instead fetch the bytes with the control's session cookies,
//       writing DIRECTLY to <GameDir>\ticket.vr1. Extract <pid>.
//    4. Launch FA.exe /NET /Name:<pid> <LaunchArgs> and close.
//
//  Uses only Windows built-ins (ole32, oleaut32, shdocvw via COM, urlmon,
//  wininet, shell32). No SDK download, no WebView2 runtime.
// ============================================================================

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <exdisp.h>       // IWebBrowser2, DWebBrowserEvents2
#include <exdispid.h>     // DISPID_* event ids
#include <mshtmhst.h>     // IDocHostUIHandler, DOCHOSTUIINFO
#include <ocidl.h>
#include <oleidl.h>
#include <shlobj.h>
#include <shellapi.h>
#include <urlmon.h>       // URLDownloadToFile
#include <servprov.h>     // IServiceProvider
#include <initguid.h>     // so DEFINE_GUID emits the GUID data in this TU
#include <downloadmgr.h>  // IDownloadManager, IID_IDownloadManager
// SID_SDownloadManager isn't defined by the MinGW headers; it equals the IID.
#ifndef SID_SDownloadManager
#define SID_SDownloadManager IID_IDownloadManager
#endif
#include <wininet.h>
#include <objbase.h>
#include <string>
#include <vector>
#include <fstream>
#include <sstream>
#include <algorithm>

// ----------------------------------------------------------------------------
//  Config (launcher.ini)
// ----------------------------------------------------------------------------
struct Config {
    std::wstring loginUrl  = L"http://localhost/login";
    std::wstring gameDir   = L"C:\\games\\FA";
    std::wstring clientExe = L"FA.exe";
    std::wstring launchArgs =
        L"/MK:0 \"/MCD1:0 /MCD2:0 /MTD:0 /NoPreload /PPS:5 /FPS:50 /SDM:1000\"";
    int windowW = 460;
    int windowH = 640;
};

static std::wstring Trim(const std::wstring& s) {
    const wchar_t* ws = L" \t\r\n";
    size_t b = s.find_first_not_of(ws);
    if (b == std::wstring::npos) return L"";
    size_t e = s.find_last_not_of(ws);
    return s.substr(b, e - b + 1);
}
static std::wstring Utf8ToWide(const std::string& s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
    return w;
}
static void ShowError(const std::wstring& m) {
    MessageBoxW(nullptr, m.c_str(), L"FA Secure Launcher", MB_OK | MB_ICONERROR);
}
static void Stage(const wchar_t* s);   // fwd: defined later, used by download/host code
static std::wstring ExeDir() {
    std::vector<wchar_t> buf(MAX_PATH);
    for (;;) {
        DWORD n = GetModuleFileNameW(nullptr, buf.data(), (DWORD)buf.size());
        if (!n) return L".";
        if (n < buf.size() - 1) break;
        buf.resize(buf.size() * 2);
    }
    std::wstring p(buf.data());
    size_t s = p.find_last_of(L"\\/");
    return (s == std::wstring::npos) ? L"." : p.substr(0, s);
}
static bool FileExists(const std::wstring& p) {
    DWORD a = GetFileAttributesW(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static bool LoadConfig(const std::wstring& ini, Config& cfg, std::wstring& err) {
    std::ifstream f(ini.c_str(), std::ios::binary);
    if (!f) { err = L"Could not open launcher.ini at:\n" + ini; return false; }
    std::stringstream ss; ss << f.rdbuf();
    std::string bytes = ss.str();
    if (bytes.size() >= 3 && (unsigned char)bytes[0] == 0xEF &&
        (unsigned char)bytes[1] == 0xBB && (unsigned char)bytes[2] == 0xBF)
        bytes.erase(0, 3);
    std::wstring text = Utf8ToWide(bytes);
    std::wstringstream lines(text); std::wstring line;
    while (std::getline(lines, line)) {
        std::wstring t = Trim(line);
        if (t.empty() || t[0] == L';' || t[0] == L'#' || t[0] == L'[') continue;
        size_t eq = t.find(L'='); if (eq == std::wstring::npos) continue;
        std::wstring k = Trim(t.substr(0, eq)), v = Trim(t.substr(eq + 1));
        if (v.size() >= 2 && v.front() == L'"' && v.back() == L'"') v = v.substr(1, v.size() - 2);
        std::wstring lk = k; std::transform(lk.begin(), lk.end(), lk.begin(), ::towlower);
        if      (lk == L"loginurl" || lk == L"serverurl" || lk == L"server") cfg.loginUrl = v;
        else if (lk == L"gamedir")    cfg.gameDir = v;
        else if (lk == L"clientexe")  cfg.clientExe = v;
        else if (lk == L"launchargs") cfg.launchArgs = v;
        else if (lk == L"windowwidth")  { try { cfg.windowW = std::stoi(v); } catch (...) {} }
        else if (lk == L"windowheight") { try { cfg.windowH = std::stoi(v); } catch (...) {} }
    }
    return true;
}

// ----------------------------------------------------------------------------
//  Globals
// ----------------------------------------------------------------------------
static Config        g_cfg;
static IWebBrowser2* g_web = nullptr;
static HWND          g_mainWnd = nullptr;
static bool          g_launched = false;
static bool          g_handling = false;   // set as soon as a download is being handled
static bool          g_docLoaded = false;  // set on DocumentComplete for the login page
static int           g_navAttempts = 0;
static std::wstring  g_pendingUrl;         // url to fetch, handed to the main thread
#define WM_DO_DOWNLOAD (WM_APP + 1)
#define WM_DO_NAVIGATE (WM_APP + 2)
#define NAV_RETRY_TIMER 1001

static bool ExtractPidFromName(const std::wstring& name, std::wstring& pid) {
    size_t a = name.rfind(L"ticket_");
    if (a == std::wstring::npos) return false;
    size_t start = a + 7;
    size_t b = name.find(L".vr1", start);
    if (b == std::wstring::npos || b <= start) return false;
    pid = name.substr(start, b - start);
    return !pid.empty();
}

static bool LaunchGame(const std::wstring& pid, std::wstring& err,
                       const std::wstring& serverClientPath = L"") {
    // Prefer the client path the WEBSITE has stored for this account (sent by the
    // server in the X-Game-Client-Path header). Fall back to launcher.ini only if
    // the server didn't provide one. This means the launcher respects whatever path
    // the user set on the web page, instead of blindly using the ini.
    std::wstring client, workDir;
    if (!serverClientPath.empty()) {
        client = serverClientPath;
        size_t slash = client.find_last_of(L"\\/");
        workDir = (slash == std::wstring::npos) ? g_cfg.gameDir : client.substr(0, slash);
    } else {
        client = g_cfg.gameDir + L"\\" + g_cfg.clientExe;
        workDir = g_cfg.gameDir;
    }
    if (!FileExists(client)) { err = L"Game client not found:\n" + client; return false; }
    std::wstring cmd = L"\"" + client + L"\" /NET /Name:" + pid + L" " + g_cfg.launchArgs;
    STARTUPINFOW si; ZeroMemory(&si, sizeof si); si.cb = sizeof si;
    PROCESS_INFORMATION pi; ZeroMemory(&pi, sizeof pi);
    std::vector<wchar_t> buf(cmd.begin(), cmd.end()); buf.push_back(0);
    if (!CreateProcessW(nullptr, buf.data(), nullptr, nullptr, FALSE, 0, nullptr,
                        workDir.c_str(), &si, &pi)) {
        wchar_t b2[128]; swprintf(b2, 128, L"CreateProcess failed (error %lu):\n", GetLastError());
        err = std::wstring(b2) + cmd; return false;
    }
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return true;
}

// Resolve a possibly-relative navigation URL against the login URL's origin so
// URLDownloadToFile always gets an absolute URL (e.g. "/download" -> "http://host/download").
static std::wstring MakeAbsolute(const std::wstring& url) {
    if (url.rfind(L"http://", 0) == 0 || url.rfind(L"https://", 0) == 0) return url;
    // derive scheme://host[:port] from loginUrl
    std::wstring base = g_cfg.loginUrl;
    size_t scheme = base.find(L"://");
    if (scheme == std::wstring::npos) return url;
    size_t hostStart = scheme + 3;
    size_t pathStart = base.find(L'/', hostStart);
    std::wstring origin = (pathStart == std::wstring::npos) ? base : base.substr(0, pathStart);
    if (!url.empty() && url[0] == L'/') return origin + url;
    return origin + L"/" + url;
}

// Fetch the ticket directly to <GameDir>\ticket.vr1 (uses WinINet cookie jar the
// WebBrowser control shares, so the authenticated /download succeeds), then launch.
// Fetch the ticket via WinINet directly into <GameDir>\ticket.vr1. Reads the PID
// from the response's Content-Disposition (filename="ticket_<pid>.vr1") since the
// /download URL itself carries no PID. WinINet shares the WebBrowser control's
// cookie jar, so the authenticated session carries automatically.
static void DownloadTicketAndLaunch(const std::wstring& rawUrl) {
    if (g_launched || g_handling) return;   // only one path may drive the fetch
    g_handling = true;
    std::wstring url = MakeAbsolute(rawUrl);
    Stage((L"D1: fetch " + url).c_str());

    // dest is decided AFTER we read the server's X-Game-Client-Path header below.
    std::wstring dest;

    // --- crack the URL into host / path / port / scheme ---
    URL_COMPONENTSW uc; ZeroMemory(&uc, sizeof uc); uc.dwStructSize = sizeof uc;
    wchar_t host[256] = L"", path[2048] = L"";
    uc.lpszHostName = host; uc.dwHostNameLength = 255;
    uc.lpszUrlPath = path;  uc.dwUrlPathLength = 2047;
    if (!InternetCrackUrlW(url.c_str(), 0, 0, &uc)) {
        ShowError(L"Could not parse the download URL:\n" + url); g_handling = false; return;
    }
    INTERNET_PORT port = uc.nPort;
    bool https = (uc.nScheme == INTERNET_SCHEME_HTTPS);

    HINTERNET hNet = InternetOpenW(L"FALauncher", INTERNET_OPEN_TYPE_PRECONFIG,
                                   nullptr, nullptr, 0);
    if (!hNet) { ShowError(L"InternetOpen failed."); g_handling = false; return; }

    HINTERNET hCon = InternetConnectW(hNet, host, port, nullptr, nullptr,
                                      INTERNET_SERVICE_HTTP, 0, 0);
    if (!hCon) { InternetCloseHandle(hNet); ShowError(L"InternetConnect failed:\n" + std::wstring(host)); g_handling = false; return; }

    DWORD flags = INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE;
    if (https) flags |= INTERNET_FLAG_SECURE;
    HINTERNET hReq = HttpOpenRequestW(hCon, L"GET", path, nullptr, nullptr, nullptr, flags, 0);
    if (!hReq) { InternetCloseHandle(hCon); InternetCloseHandle(hNet);
                 ShowError(L"HttpOpenRequest failed."); g_handling = false; return; }

    // Attach the WebBrowser control's session cookie for this URL so /download
    // sees us as logged in. (WinINet usually shares the jar, but set it explicitly
    // to be safe against process-isolated cookies.)
    {
        DWORD clen = 0;
        InternetGetCookieExW(url.c_str(), nullptr, nullptr, &clen, INTERNET_COOKIE_HTTPONLY, 0);
        if (clen) {
            std::wstring cookie(clen, L'\0');
            if (InternetGetCookieExW(url.c_str(), nullptr, &cookie[0], &clen,
                                     INTERNET_COOKIE_HTTPONLY, 0)) {
                if (!cookie.empty() && cookie.back() == L'\0') cookie.pop_back();
                std::wstring hdr = L"Cookie: " + cookie + L"\r\n";
                HttpAddRequestHeadersW(hReq, hdr.c_str(), (DWORD)-1,
                                       HTTP_ADDREQ_FLAG_ADD | HTTP_ADDREQ_FLAG_REPLACE);
            }
        }
    }

    if (!HttpSendRequestW(hReq, nullptr, 0, nullptr, 0)) {
        InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);
        ShowError(L"HttpSendRequest failed for:\n" + url); g_handling = false; return;
    }

    // Check HTTP status.
    DWORD status = 0, slen = sizeof(status);
    HttpQueryInfoW(hReq, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER, &status, &slen, nullptr);
    if (status != 200) {
        InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);
        wchar_t b[128]; swprintf(b, 128, L"The server returned HTTP %lu for the ticket download.\n"
                                         L"(Are you logged in?)", status);
        ShowError(b); g_handling = false; return;
    }

    // Read the PID from Content-Disposition: attachment; filename="ticket_<pid>.vr1"
    std::wstring pid;
    {
        wchar_t cd[512] = L""; DWORD cdlen = sizeof(cd);
        if (HttpQueryInfoW(hReq, HTTP_QUERY_CONTENT_DISPOSITION, cd, &cdlen, nullptr))
            ExtractPidFromName(cd, pid);
    }

    // Read the account's stored client path from the server (X-Game-Client-Path).
    // This overrides launcher.ini so the launcher uses whatever path the website has.
    std::wstring serverClientPath, gameDir = g_cfg.gameDir;
    {
        wchar_t hv[1024] = L""; DWORD hl = sizeof(hv);
        // HTTP_QUERY_CUSTOM: put the header name in the buffer first.
        wcscpy(hv, L"X-Game-Client-Path");
        if (HttpQueryInfoW(hReq, HTTP_QUERY_CUSTOM, hv, &hl, nullptr) && hv[0]) {
            serverClientPath = hv;
            size_t slash = serverClientPath.find_last_of(L"\\/");
            if (slash != std::wstring::npos) gameDir = serverClientPath.substr(0, slash);
        }
    }
    dest = gameDir + L"\\ticket.vr1";
    if (FileExists(dest)) DeleteFileW(dest.c_str());

    // Stream the body to <GameDir>\ticket.vr1.
    HANDLE hf = CreateFileW(dest.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                            FILE_ATTRIBUTE_NORMAL, nullptr);
    if (hf == INVALID_HANDLE_VALUE) {
        InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);
        ShowError(L"Could not create:\n" + dest + L"\n(Check GameDir is writable.)"); g_handling = false; return;
    }
    BYTE buf[8192]; DWORD got = 0; DWORD total = 0;
    while (InternetReadFile(hReq, buf, sizeof buf, &got) && got > 0) {
        DWORD wr = 0; WriteFile(hf, buf, got, &wr, nullptr); total += wr;
    }
    CloseHandle(hf);
    InternetCloseHandle(hReq); InternetCloseHandle(hCon); InternetCloseHandle(hNet);

    if (total == 0 || !FileExists(dest)) {
        ShowError(L"The ticket download was empty.\nURL:\n" + url); g_handling = false; return;
    }
    Stage((L"D2: saved " + std::to_wstring(total) + L" bytes, pid=" + pid).c_str());

    if (pid.empty()) {
        ShowError(L"Ticket saved to " + dest + L", but the PID could not be read from the "
                  L"server's Content-Disposition header.\n\nThe game was not launched.");
        g_handling = false; return;
    }

    std::wstring err;
    if (!LaunchGame(pid, err, serverClientPath)) { ShowError(err); g_handling = false; return; }
    g_launched = true;
    if (g_mainWnd) PostMessageW(g_mainWnd, WM_CLOSE, 0, 0);
}

// ============================================================================
//  ActiveX host for the WebBrowser control.
//
//  IMPORTANT: IOleInPlaceSite and IOleInPlaceFrame BOTH derive from IOleWindow,
//  so a single class implementing both has two conflicting IOleWindow vtables ->
//  the control's callback lands on the wrong slot -> access violation (0xC0000005)
//  during DoVerb activation. We therefore split the frame into its OWN object
//  (InPlaceFrame) and keep the site interfaces on Host. Each object has exactly
//  one IOleWindow, so every vtable is well-formed.
// ============================================================================

class Host;   // fwd

// -- The in-place frame: its own object, single IOleWindow lineage. -----------
class InPlaceFrame : public IOleInPlaceFrame {
public:
    LONG ref = 1;
    HWND hwnd = nullptr;
    explicit InPlaceFrame(HWND h) : hwnd(h) {}
    virtual ~InPlaceFrame() {}

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IOleWindow || riid == IID_IOleInPlaceUIWindow ||
            riid == IID_IOleInPlaceFrame) {
            *ppv = static_cast<IOleInPlaceFrame*>(this); AddRef(); return S_OK;
        }
        *ppv = nullptr; return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref); }
    STDMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&ref); if (!r) delete this; return r; }

    // IOleWindow
    STDMETHODIMP GetWindow(HWND* p) override { if (!p) return E_POINTER; *p = hwnd; return S_OK; }
    STDMETHODIMP ContextSensitiveHelp(BOOL) override { return S_OK; }
    // IOleInPlaceUIWindow
    STDMETHODIMP GetBorder(LPRECT) override { return E_NOTIMPL; }
    STDMETHODIMP RequestBorderSpace(LPCBORDERWIDTHS) override { return E_NOTIMPL; }
    STDMETHODIMP SetBorderSpace(LPCBORDERWIDTHS) override { return S_OK; }
    STDMETHODIMP SetActiveObject(IOleInPlaceActiveObject*, LPCOLESTR) override { return S_OK; }
    // IOleInPlaceFrame
    STDMETHODIMP InsertMenus(HMENU, LPOLEMENUGROUPWIDTHS) override { return S_OK; }
    STDMETHODIMP SetMenu(HMENU, HOLEMENU, HWND) override { return S_OK; }
    STDMETHODIMP RemoveMenus(HMENU) override { return S_OK; }
    STDMETHODIMP SetStatusText(LPCOLESTR) override { return S_OK; }
    STDMETHODIMP EnableModeless(BOOL) override { return S_OK; }
    STDMETHODIMP TranslateAccelerator(LPMSG, WORD) override { return S_FALSE; }
};

// -- The site: IOleClientSite + IOleInPlaceSite + IDocHostUIHandler + events. --
//    Single IOleWindow (via IOleInPlaceSite), so no vtable collision.
class Host :
    public IOleClientSite,
    public IOleInPlaceSite,
    public IStorage,
    public IDocHostUIHandler,
    public IServiceProvider,
    public IDownloadManager,
    public DWebBrowserEvents2 {
public:
    LONG ref = 1;
    HWND hwnd = nullptr;
    DWORD cookie = 0;
    InPlaceFrame* frame = nullptr;
    explicit Host(HWND h) : hwnd(h) { frame = new InPlaceFrame(h); }
    virtual ~Host() { if (frame) frame->Release(); }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (riid == IID_IUnknown || riid == IID_IOleClientSite) *ppv = static_cast<IOleClientSite*>(this);
        else if (riid == IID_IOleInPlaceSite) *ppv = static_cast<IOleInPlaceSite*>(this);
        else if (riid == IID_IOleWindow)      *ppv = static_cast<IOleWindow*>(static_cast<IOleInPlaceSite*>(this));
        else if (riid == IID_IStorage)        *ppv = static_cast<IStorage*>(this);
        else if (riid == IID_IDocHostUIHandler) *ppv = static_cast<IDocHostUIHandler*>(this);
        else if (riid == IID_IServiceProvider)  *ppv = static_cast<IServiceProvider*>(this);
        else if (riid == IID_IDownloadManager)  *ppv = static_cast<IDownloadManager*>(this);
        else if (riid == IID_IDispatch || riid == DIID_DWebBrowserEvents2)
            *ppv = static_cast<DWebBrowserEvents2*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref); }
    STDMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&ref); if (!r) delete this; return r; }

    // IServiceProvider: hand IE our IDownloadManager so ALL downloads route to us
    // (no browser download dialog ever appears).
    STDMETHODIMP QueryService(REFGUID guidService, REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (guidService == SID_SDownloadManager && riid == IID_IDownloadManager) {
            *ppv = static_cast<IDownloadManager*>(this); AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }

    // IDownloadManager::Download - called by IE for every download instead of its
    // own dialog. We ignore the moniker/bind params and just fetch the ticket.
    STDMETHODIMP Download(IMoniker* pmk, IBindCtx*, DWORD, LONG, BINDINFO*,
                          LPCOLESTR, LPCOLESTR, UINT) override {
        std::wstring url;
        if (pmk) {
            LPOLESTR name = nullptr;
            if (SUCCEEDED(pmk->GetDisplayName(nullptr, nullptr, &name)) && name) {
                url = name; CoTaskMemFree(name);
            }
        }
        Stage((L"9d: IDownloadManager url=" + url).c_str());
        if (!g_launched && !g_handling && hwnd) {
            g_pendingUrl = url.empty() ? L"/download" : url;
            PostMessageW(hwnd, WM_DO_DOWNLOAD, 0, 0);
        }
        return S_OK;   // we handled it; IE shows no dialog
    }

    // IOleClientSite
    STDMETHODIMP SaveObject() override { return S_OK; }
    STDMETHODIMP GetMoniker(DWORD, DWORD, IMoniker** m) override { if (m) *m = nullptr; return E_NOTIMPL; }
    STDMETHODIMP GetContainer(IOleContainer** c) override { if (c) *c = nullptr; return E_NOINTERFACE; }
    STDMETHODIMP ShowObject() override { return S_OK; }
    STDMETHODIMP OnShowWindow(BOOL) override { return S_OK; }
    STDMETHODIMP RequestNewObjectLayout() override { return E_NOTIMPL; }

    // IOleWindow / IOleInPlaceSite
    STDMETHODIMP GetWindow(HWND* p) override { if (!p) return E_POINTER; *p = hwnd; return S_OK; }
    STDMETHODIMP ContextSensitiveHelp(BOOL) override { return S_OK; }
    STDMETHODIMP CanInPlaceActivate() override { return S_OK; }
    STDMETHODIMP OnInPlaceActivate() override { return S_OK; }
    STDMETHODIMP OnUIActivate() override { return S_OK; }
    STDMETHODIMP GetWindowContext(IOleInPlaceFrame** ppFrame, IOleInPlaceUIWindow** doc,
                                  LPRECT r, LPRECT cr, LPOLEINPLACEFRAMEINFO fi) override {
        if (ppFrame) { *ppFrame = frame; frame->AddRef(); }
        if (doc) *doc = nullptr;
        RECT rc; GetClientRect(hwnd, &rc);
        if (r)  *r = rc;
        if (cr) *cr = rc;
        if (fi) { fi->cb = sizeof(OLEINPLACEFRAMEINFO); fi->fMDIApp = FALSE;
                  fi->hwndFrame = hwnd; fi->haccel = nullptr; fi->cAccelEntries = 0; }
        return S_OK;
    }
    STDMETHODIMP Scroll(SIZE) override { return S_OK; }
    STDMETHODIMP OnUIDeactivate(BOOL) override { return S_OK; }
    STDMETHODIMP OnInPlaceDeactivate() override { return S_OK; }
    STDMETHODIMP DiscardUndoState() override { return S_OK; }
    STDMETHODIMP DeactivateAndUndo() override { return S_OK; }
    STDMETHODIMP OnPosRectChange(LPCRECT) override { return S_OK; }

    // IStorage (stubs)
    STDMETHODIMP CreateStream(const OLECHAR*, DWORD, DWORD, DWORD, IStream**) override { return E_NOTIMPL; }
    STDMETHODIMP OpenStream(const OLECHAR*, void*, DWORD, DWORD, IStream**) override { return E_NOTIMPL; }
    STDMETHODIMP CreateStorage(const OLECHAR*, DWORD, DWORD, DWORD, IStorage**) override { return E_NOTIMPL; }
    STDMETHODIMP OpenStorage(const OLECHAR*, IStorage*, DWORD, SNB, DWORD, IStorage**) override { return E_NOTIMPL; }
    STDMETHODIMP CopyTo(DWORD, const IID*, SNB, IStorage*) override { return E_NOTIMPL; }
    STDMETHODIMP MoveElementTo(const OLECHAR*, IStorage*, const OLECHAR*, DWORD) override { return E_NOTIMPL; }
    STDMETHODIMP Commit(DWORD) override { return E_NOTIMPL; }
    STDMETHODIMP Revert() override { return E_NOTIMPL; }
    STDMETHODIMP EnumElements(DWORD, void*, DWORD, IEnumSTATSTG**) override { return E_NOTIMPL; }
    STDMETHODIMP DestroyElement(const OLECHAR*) override { return E_NOTIMPL; }
    STDMETHODIMP RenameElement(const OLECHAR*, const OLECHAR*) override { return E_NOTIMPL; }
    STDMETHODIMP SetElementTimes(const OLECHAR*, const FILETIME*, const FILETIME*, const FILETIME*) override { return E_NOTIMPL; }
    STDMETHODIMP SetClass(REFCLSID) override { return S_OK; }
    STDMETHODIMP SetStateBits(DWORD, DWORD) override { return E_NOTIMPL; }
    STDMETHODIMP Stat(STATSTG*, DWORD) override { return E_NOTIMPL; }

    // IDocHostUIHandler
    STDMETHODIMP ShowContextMenu(DWORD, POINT*, IUnknown*, IDispatch*) override { return S_OK; }
    STDMETHODIMP GetHostInfo(DOCHOSTUIINFO* i) override {
        if (!i) return E_POINTER;
        i->cbSize = sizeof(DOCHOSTUIINFO);
        i->dwFlags = DOCHOSTUIFLAG_NO3DBORDER | DOCHOSTUIFLAG_FLAT_SCROLLBAR;
        i->dwDoubleClick = DOCHOSTUIDBLCLK_DEFAULT;
        return S_OK;
    }
    STDMETHODIMP ShowUI(DWORD, IOleInPlaceActiveObject*, IOleCommandTarget*,
                        IOleInPlaceFrame*, IOleInPlaceUIWindow*) override { return S_OK; }
    STDMETHODIMP HideUI() override { return S_OK; }
    STDMETHODIMP UpdateUI() override { return S_OK; }
    STDMETHODIMP EnableModeless(BOOL) override { return S_OK; }
    STDMETHODIMP OnDocWindowActivate(BOOL) override { return S_OK; }
    STDMETHODIMP OnFrameWindowActivate(BOOL) override { return S_OK; }
    STDMETHODIMP ResizeBorder(LPCRECT, IOleInPlaceUIWindow*, BOOL) override { return S_OK; }
    STDMETHODIMP TranslateAccelerator(LPMSG, const GUID*, DWORD) override { return S_FALSE; }
    STDMETHODIMP GetOptionKeyPath(LPOLESTR* k, DWORD) override { if (k) *k = nullptr; return S_FALSE; }
    STDMETHODIMP GetDropTarget(IDropTarget*, IDropTarget** t) override { if (t) *t = nullptr; return E_NOTIMPL; }
    STDMETHODIMP GetExternal(IDispatch** d) override { if (d) *d = nullptr; return E_NOTIMPL; }
    STDMETHODIMP TranslateUrl(DWORD, LPWSTR, LPWSTR* out) override { if (out) *out = nullptr; return E_NOTIMPL; }
    STDMETHODIMP FilterDataObject(IDataObject*, IDataObject** o) override { if (o) *o = nullptr; return E_NOTIMPL; }

    // IDispatch (event sink)
    STDMETHODIMP GetTypeInfoCount(UINT* c) override { if (c) *c = 0; return E_NOTIMPL; }
    STDMETHODIMP GetTypeInfo(UINT, LCID, ITypeInfo** t) override { if (t) *t = nullptr; return E_NOTIMPL; }
    STDMETHODIMP GetIDsOfNames(REFIID, LPOLESTR*, UINT, LCID, DISPID*) override { return E_NOTIMPL; }
    STDMETHODIMP Invoke(DISPID dispId, REFIID, LCID, WORD wFlags, DISPPARAMS* p,
                        VARIANT*, EXCEPINFO*, UINT*) override {
        // BeforeNavigate2: catch the navigation to /download, cancel it, fetch ourselves.
        // DocumentComplete: the login page finished loading. Mark it so the retry
        // timer stops re-navigating.
        if (dispId == DISPID_DOCUMENTCOMPLETE) {
            g_docLoaded = true;
            Stage(L"L: DocumentComplete");
            return S_OK;
        }

        if (dispId == DISPID_BEFORENAVIGATE2) {
            if (!(wFlags & DISPATCH_METHOD) || !p || !p->rgvarg || p->cArgs < 7) return S_OK;
            // The URL is normally rgvarg[5] as VT_BYREF|VT_BSTR, but depending on how the
            // navigation was initiated it can be a plain BSTR, or a VARIANT* wrapping one.
            // Resolve all of those, and if index 5 is empty, scan the other args for a BSTR
            // that looks like a URL (contains "://" or starts with "/").
            auto readBstr = [](VARIANT& v) -> std::wstring {
                VARIANT* pv = &v;
                if (pv->vt == (VT_BYREF | VT_VARIANT) && pv->pvarVal) pv = pv->pvarVal;
                if (pv->vt == (VT_BYREF | VT_BSTR)) return (pv->pbstrVal && *pv->pbstrVal) ? *pv->pbstrVal : L"";
                if (pv->vt == VT_BSTR)              return pv->bstrVal ? pv->bstrVal : L"";
                return L"";
            };
            std::wstring url = readBstr(p->rgvarg[5]);
            if (url.empty()) {
                for (UINT i = 0; i < p->cArgs; ++i) {
                    std::wstring cand = readBstr(p->rgvarg[i]);
                    if (cand.find(L"://") != std::wstring::npos ||
                        (!cand.empty() && cand[0] == L'/')) { url = cand; break; }
                }
            }

            { wchar_t vb[64]; swprintf(vb, 64, L"9b: BeforeNavigate2 vt=0x%04x url=", p->rgvarg[5].vt);
              std::wstring s = std::wstring(vb) + url; Stage(s.c_str()); }

            if (!url.empty()) {
                std::wstring low = url;
                std::transform(low.begin(), low.end(), low.begin(), ::towlower);
                if (low.find(L"/download") != std::wstring::npos ||
                    low.find(L"ticket_") != std::wstring::npos) {
                    VARIANT& vCancel = p->rgvarg[0];
                    if (vCancel.vt == (VT_BYREF | VT_BOOL) && vCancel.pboolVal)
                        *vCancel.pboolVal = VARIANT_TRUE;   // stop the browser's navigation/download
                    if (!g_launched && !g_handling && hwnd) {
                        g_pendingUrl = url;
                        PostMessageW(hwnd, WM_DO_DOWNLOAD, 0, 0);
                    }
                }
            }
            return S_OK;
        }

        // FileDownload: fires when a response is an attachment. If our BeforeNavigate2
        // catch missed (some IE builds skip it for direct attachment links), grab the
        // last navigated URL here and handle it, cancelling the browser's dialog.
        if (dispId == DISPID_FILEDOWNLOAD) {
            Stage(L"9c: FileDownload event");
            // Cancel the browser download dialog (arg[0] = Cancel, VT_BOOL|VT_BYREF).
            if (p && p->rgvarg && p->cArgs >= 1 &&
                p->rgvarg[0].vt == (VT_BOOL | VT_BYREF) && p->rgvarg[0].pboolVal)
                *p->rgvarg[0].pboolVal = VARIANT_TRUE;
            // Fetch using the URL the browser is currently pointed at.
            if (!g_launched && !g_handling && g_web && hwnd) {
                BSTR loc = nullptr;
                if (SUCCEEDED(g_web->get_LocationURL(&loc)) && loc) {
                    std::wstring url = loc; SysFreeString(loc);
                    std::wstring low = url;
                    std::transform(low.begin(), low.end(), low.begin(), ::towlower);
                    if (low.find(L"/download") != std::wstring::npos ||
                        low.find(L"ticket_") != std::wstring::npos) {
                        g_pendingUrl = url;
                        PostMessageW(hwnd, WM_DO_DOWNLOAD, 0, 0);
                    }
                }
            }
            return S_OK;
        }

        return S_OK;
    }
};

// ----------------------------------------------------------------------------
//  Control lifecycle
// ----------------------------------------------------------------------------
static Host*             g_host = nullptr;
static IOleObject*       g_oleObj = nullptr;
static IConnectionPoint* g_cp = nullptr;

// Write the current startup stage to <ExeDir>\launcher_stage.txt so that if the
// process dies hard (0xC0000005) we can still see exactly which call crashed.
static void Stage(const wchar_t* s) {
    static std::wstring path = ExeDir() + L"\\launcher_stage.txt";
    HANDLE h = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ, nullptr,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h != INVALID_HANDLE_VALUE) {
        SetFilePointer(h, 0, nullptr, FILE_END);
        std::string a; for (const wchar_t* p = s; *p; ++p) a += (char)*p;
        a += "\r\n";
        DWORD wr; WriteFile(h, a.c_str(), (DWORD)a.size(), &wr, nullptr);
        FlushFileBuffers(h);
        CloseHandle(h);
    }
}

static bool CreateBrowser(HWND hwnd) {
    Stage(L"1: new Host");
    g_host = new Host(hwnd);

    Stage(L"2: CoCreateInstance(WebBrowser)");
    IOleObject* ole = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_WebBrowser, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_IOleObject, (void**)&ole);
    if (FAILED(hr) || !ole) {
        wchar_t b[128]; swprintf(b, 128, L"CoCreateInstance(WebBrowser) failed: hr=0x%08lX", hr);
        ShowError(b); return false;
    }
    g_oleObj = ole;

    Stage(L"3: SetClientSite");
    ole->SetClientSite(g_host);
    ole->SetHostNames(L"FALauncher", nullptr);

    RECT rc; GetClientRect(hwnd, &rc);
    Stage(L"4: OleSetContainedObject");
    OleSetContainedObject(ole, TRUE);
    Stage(L"5: DoVerb(INPLACEACTIVATE)");
    hr = ole->DoVerb(OLEIVERB_INPLACEACTIVATE, nullptr, g_host, 0, hwnd, &rc);
    if (FAILED(hr)) {
        wchar_t b[128]; swprintf(b, 128, L"DoVerb(INPLACEACTIVATE) failed: hr=0x%08lX", hr);
        ShowError(b); return false;
    }

    Stage(L"6: QI(IWebBrowser2)");
    hr = ole->QueryInterface(IID_IWebBrowser2, (void**)&g_web);
    if (FAILED(hr) || !g_web) {
        wchar_t b[128]; swprintf(b, 128, L"QI(IWebBrowser2) failed: hr=0x%08lX", hr);
        ShowError(b); return false;
    }

    Stage(L"7: Advise events");
    IConnectionPointContainer* cpc = nullptr;
    if (SUCCEEDED(ole->QueryInterface(IID_IConnectionPointContainer, (void**)&cpc)) && cpc) {
        if (SUCCEEDED(cpc->FindConnectionPoint(DIID_DWebBrowserEvents2, &g_cp)) && g_cp)
            g_cp->Advise(static_cast<IDispatch*>(static_cast<DWebBrowserEvents2*>(g_host)), &g_host->cookie);
        cpc->Release();
    }

    Stage(L"8: size control");
    g_web->put_Left(0); g_web->put_Top(0);
    g_web->put_Width(rc.right - rc.left);
    g_web->put_Height(rc.bottom - rc.top);

    Stage(L"9: Navigate");
    {
        BSTR url = SysAllocString(g_cfg.loginUrl.c_str());
        HRESULT hn = g_web->Navigate(url, nullptr, nullptr, nullptr, nullptr);
        SysFreeString(url);
        g_navAttempts = 1;
        if (FAILED(hn)) {
            wchar_t b[128]; swprintf(b, 128, L"Navigate failed: hr=0x%08lX", hn);
            ShowError(b); return false;
        }
        // Reliability: the legacy control sometimes accepts the navigation but the
        // page never renders (spins/blank). Start a timer that re-navigates if the
        // login page hasn't fired DocumentComplete within a couple seconds.
        SetTimer(hwnd, NAV_RETRY_TIMER, 2500, nullptr);
    }
    Stage(L"10: done");
    return true;
}

static void DestroyBrowser() {
    if (g_cp && g_host) { g_cp->Unadvise(g_host->cookie); g_cp->Release(); g_cp = nullptr; }
    if (g_web) { g_web->Release(); g_web = nullptr; }
    if (g_oleObj) { g_oleObj->Close(OLECLOSE_NOSAVE); g_oleObj->SetClientSite(nullptr); g_oleObj->Release(); g_oleObj = nullptr; }
    if (g_host) { g_host->Release(); g_host = nullptr; }
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_TIMER:
        if (wp == NAV_RETRY_TIMER) {
            if (g_docLoaded || g_launched) {
                KillTimer(hwnd, NAV_RETRY_TIMER);   // page loaded (or we're launching) - stop
            } else if (g_navAttempts < 5 && g_web) {
                // Page still hasn't rendered - re-navigate. Fixes the intermittent
                // "spins/blank" first-load of the legacy control.
                g_navAttempts++;
                Stage((L"R: retry navigate #" + std::to_wstring(g_navAttempts)).c_str());
                BSTR url = SysAllocString(g_cfg.loginUrl.c_str());
                g_web->Navigate(url, nullptr, nullptr, nullptr, nullptr);
                SysFreeString(url);
            } else {
                KillTimer(hwnd, NAV_RETRY_TIMER);   // give up retrying; leave what we have
            }
        }
        return 0;
    case WM_DO_DOWNLOAD:
        // Runs on the main thread, AFTER the browser event that posted it has
        // returned — so the WinINet fetch no longer races IE's in-flight navigation.
        if (!g_pendingUrl.empty()) {
            std::wstring u = g_pendingUrl; g_pendingUrl.clear();
            DownloadTicketAndLaunch(u);
        }
        return 0;
    case WM_SIZE:
        if (g_web) { g_web->put_Width(LOWORD(lp)); g_web->put_Height(HIWORD(lp)); }
        return 0;
    case WM_DESTROY:
        DestroyBrowser();
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

// ----------------------------------------------------------------------------
//  Entry point
// ----------------------------------------------------------------------------
// Vectored exception handler: catches an access violation during control hosting
// and reports it (instead of the process dying silently), then lets the default
// handler terminate. Registered only around the browser-creation call.
static LONG WINAPI StartupVEH(EXCEPTION_POINTERS* ep) {
    DWORD code = ep && ep->ExceptionRecord ? ep->ExceptionRecord->ExceptionCode : 0;
    // Only report genuine faults, not C++/debug exceptions.
    if (code == EXCEPTION_ACCESS_VIOLATION ||
        code == EXCEPTION_ILLEGAL_INSTRUCTION ||
        code == EXCEPTION_IN_PAGE_ERROR ||
        code == EXCEPTION_PRIV_INSTRUCTION) {
        wchar_t b[256];
        swprintf(b, 256,
                 L"The launcher crashed while starting the embedded browser "
                 L"(exception 0x%08lX at %p).\n\nThe built-in Internet Explorer / "
                 L"MSHTML control appears unavailable for hosting on this system.",
                 code, ep && ep->ExceptionRecord ? ep->ExceptionRecord->ExceptionAddress : nullptr);
        MessageBoxW(nullptr, b, L"FA Secure Launcher", MB_OK | MB_ICONERROR);
    }
    return EXCEPTION_CONTINUE_SEARCH;   // let normal termination proceed after the box
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR, int nCmd) {
    HRESULT co = OleInitialize(nullptr);
    if (FAILED(co)) { ShowError(L"OLE initialisation failed."); return 1; }

    std::wstring ini = ExeDir() + L"\\launcher.ini", err;
    if (!LoadConfig(ini, g_cfg, err)) {
        ShowError(err + L"\n\nExpected an INI next to the launcher, e.g.:\n\n"
                        L"[Launcher]\nLoginUrl=http://localhost/login\nGameDir=C:\\games\\FA");
        OleUninitialize(); return 1;
    }
    // NOTE: we deliberately do NOT hard-fail here if GameDir is missing. The real
    // client path normally arrives from the server (X-Game-Client-Path header) at
    // launch time; GameDir/ClientExe in the ini are only a fallback. Validating the
    // client path happens in LaunchGame, which reports a clear error if neither the
    // server path nor the fallback resolves to a real FA.exe.

    WNDCLASSW wc; ZeroMemory(&wc, sizeof wc);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"FALauncherWnd";
    RegisterClassW(&wc);

    int W = g_cfg.windowW, H = g_cfg.windowH;
    int sx = (GetSystemMetrics(SM_CXSCREEN) - W) / 2;
    int sy = (GetSystemMetrics(SM_CYSCREEN) - H) / 2;
    g_mainWnd = CreateWindowW(L"FALauncherWnd", L"FA Secure Launcher",
                              WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
                              sx, sy, W, H, nullptr, nullptr, hInst, nullptr);
    if (!g_mainWnd) { ShowError(L"Could not create the launcher window."); OleUninitialize(); return 1; }

    // Realise the window BEFORE hosting the control: the WebBrowser control's
    // in-place activation needs a shown window with a valid client rect, or it
    // can fail/fault. (Doing this after CreateBrowser was the blank/no-window bug.)
    ShowWindow(g_mainWnd, nCmd);
    UpdateWindow(g_mainWnd);

    PVOID veh = AddVectoredExceptionHandler(1, StartupVEH);
    bool browserOk = CreateBrowser(g_mainWnd);
    if (veh) RemoveVectoredExceptionHandler(veh);
    if (!browserOk) {
        // CreateBrowser already showed a specific ShowError (HRESULT), or the VEH
        // reported a crash. Just clean up.
        DestroyWindow(g_mainWnd); OleUninitialize(); return 1;
    }

    // Window is already shown; make sure the freshly-hosted control gets sized.
    { RECT rc; GetClientRect(g_mainWnd, &rc);
      if (g_web) { g_web->put_Width(rc.right - rc.left); g_web->put_Height(rc.bottom - rc.top); } }

    MSG m;
    while (GetMessageW(&m, nullptr, 0, 0)) {
        TranslateMessage(&m);
        DispatchMessageW(&m);
    }

    OleUninitialize();
    return 0;
}
