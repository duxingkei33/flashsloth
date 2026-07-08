// ====== 全局共享状态变量 ======
let _searchTimer = null;
let _currentSort = 'platform';
let _sortAsc = true;
let currentAccountId = 0;
let _presetsData = {};
let _loginPlatform = '';
let _loginMethod = 'cookie';
let _loginSession = null;
let _isLoginRunning = false;
var _scanMethodRetryCount = 0;
let _loginGuide = null;
let _loginCapData = null;
let _loginOAuthProvider = null;
let _platformSearchTimer = null;
let _platformSearchData = [];
let _platformSearchIdx = -1;
var _platIconsMap = {
    'discuz': '💬', 'amobbs': '💬', 'mydigit': '💬',
    'oshwhub': '🔧', 'oshwhub_eda': '⚡',
    'csdn': '📝', 'cnblogs': '📖',
    'zhihu': '❓', 'bilibili': '📺', 'juejin': '🥇',
    'wechat': '💬', 'wechat_mp': '📢',
    'xianyu': '🐟', 'xianyu_v2': '🐟', 'taobao': '🛒',
    'wordpress': '🔗', 'github_pages': '📄', 'github_pages_blog': '📄',
    'static_site': '🌐', 'github': '🐙',
    'douyin': '🎵', 'kuaishou': '📱', 'xiaohongshu': '📕',
    'tieba': '📋', 'jianshu': '✍️', 'medium': '✏️',
    'segmentfault': '💻', 'v2ex': '🔶', 'hackernews': '🔴',
    'qqzone': '💫', 'weibo': '📢', 'toutiao': '📰',
    'default': '🔑'
};
var _platColorsMap = {
    'discuz': '#e8f5e9', 'amobbs': '#e3f2fd', 'mydigit': '#fce4ec',
    'oshwhub': '#fff3e0', 'oshwhub_eda': '#fff8e1',
    'csdn': '#e8eaf6', 'cnblogs': '#f3e5f5',
    'zhihu': '#e0f2f1', 'bilibili': '#fce4ec', 'juejin': '#e8f5e9',
    'wechat': '#e8f5e9', 'wechat_mp': '#e3f2fd',
    'xianyu': '#fff3e0', 'xianyu_v2': '#fff3e0', 'taobao': '#fce4ec',
    'wordpress': '#e8eaf6', 'github_pages': '#f5f5f5', 'github_pages_blog': '#f5f5f5',
    'static_site': '#f5f5f5', 'github': '#f5f5f5',
    'douyin': '#fce4ec', 'kuaishou': '#fff3e0', 'xiaohongshu': '#fce4ec',
    'tieba': '#e3f2fd', 'jianshu': '#f3e5f5', 'medium': '#f5f5f5',
    'segmentfault': '#e8f5e9', 'v2ex': '#fff8e1', 'hackernews': '#fce4ec',
    'qqzone': '#e3f2fd', 'weibo': '#fce4ec', 'toutiao': '#fff3e0',
    'default': '#f0f4ff'
};
var _qrSessionId = null;
var _qrPollTimer = null;
var _selectedScanMethod = null;
var _origFormTitle = '➕ 添加账号 — ';
