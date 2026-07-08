// ====== 添加账号/编辑账号弹窗 + 登录渲染 ======

// ====== 添加账号弹窗 ======
function onAddAccount() {
    var input = document.getElementById('platformSearchInput');
    var platform = input.dataset.selected;
    if (!platform) { alert('请先选择一个平台'); return; }

    _loginPlatform = platform;
    _loginMethod = 'cookie';
    _loginSession = null;
    _isLoginRunning = false;

    // 先确保弹窗可见（防止上次关闭后的状态残留）
    document.getElementById('addFormBox').style.display = 'flex';
    document.getElementById('addPlatInput').value = platform;
    document.getElementById('addPlatName').textContent = input.placeholder.replace('✅ ', '');
    document.getElementById('addAccountName').value = '';
    document.getElementById('debugCookieArea').style.display = 'none';
    document.getElementById('addFormTitle').innerHTML = '➕ 添加账号 — <span id="addPlatName">' + escapeHtml(input.placeholder.replace('✅ ', '')) + '</span>';

    // 从后端动态获取登录能力（异步渲染内容）
    fetch('/api/platform/' + _loginPlatform + '/login-capabilities')
    .then(safeJson)
    .then(function(data) {
        try {
            _loginGuide = data.guide || null;
            _loginCapData = data;
            if (!data.success) {
                let methods = [];
                try {
                    var plat = _loginPlatform;
                    for (var i = 0; i < _platformSearchData.length; i++) {
                        if (_platformSearchData[i].name === plat) {
                            methods = _platformSearchData[i].login_methods || [];
                            break;
                        }
                    }
                } catch(e) {}
                renderFromLoginMethods(methods);
                return;
            }

            var methods = data.login_methods || [];
            if (methods.length === 0) {
                // 返回空方法列表 → 显示「待适配」状态
                renderWaitingForAdaptation(data);
                return;
            }

            renderLoginCapabilityTabs(methods, data.note || '');
            if (methods.length > 0) {
                selectCapabilityLoginMethod(methods[0].method, methods);
            }

            // Auto-fill site_url from API response
            if (data.site_url_default) {
                autoFillSiteUrl(data.site_url_default);
            }
        } catch(e) {
            console.error('渲染登录能力失败:', e);
            renderWaitingForAdaptation(null);
        }
    })
    .catch(function() {
        _loginGuide = null;
        renderWaitingForAdaptation(null);
    });
}

// ====== 待适配状态渲染 ======
function renderWaitingForAdaptation(data) {
    const tabsDiv = document.getElementById('loginMethodTabs');
    const contentDiv = document.getElementById('loginMethodContent');
    tabsDiv.innerHTML = '';
    var note = (data && data.note) || '该平台已探索但尚未适配登录方式';

    contentDiv.innerHTML = '<div style="padding:20px;text-align:center;background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;">'
        + '<div style="font-size:32px;margin-bottom:8px;">🔧</div>'
        + '<div style="font-size:15px;font-weight:600;color:#996600;margin-bottom:10px;">' + escapeHtml(note) + '</div>'
        + '<div style="font-size:12px;color:#888;line-height:1.6;">'
        + '该平台已有探索数据，但尚未适配完整的登录方式。<br>'
        + '您仍然可以通过「Cookie粘贴」方式添加账号。<br>'
        + '如需适配登录，请联系管理员或提交 PR。</div>'
        + '</div>';

    document.getElementById('btnStartLogin').style.display = 'none';
    document.getElementById('btnCaptchaLogin').style.display = 'none';
    document.getElementById('btnRefreshScreenshot').style.display = 'none';
    document.getElementById('loginScreenshotArea').style.display = 'none';
    document.getElementById('btnTestConnectionAdd').style.display = 'none';
    document.getElementById('loginStatusMsg').style.display = 'none';

    // 显示 Cookie 输入框（通用备选方案）
    var cookieHtml = '<div style="margin-top:12px;padding:12px;background:#f8f9ff;border:1px solid #d0d5f0;border-radius:8px;">'
        + '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">🍪 Cookie粘贴（备选方案）</div>'
        + '<div class="form-group"><label>Cookie <span style="color:#999;font-size:12px;">（从浏览器 F12 复制）</span></label>'
        + '<textarea name="cfg_cookie" rows="3" placeholder="粘贴完整的 Cookie 字符串"'
        + ' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-family:monospace;font-size:11px;"></textarea></div>'
        + '<div style="font-size:11px;color:#888;margin-top:4px;">💡 手动登录该平台后，从浏览器开发者工具复制 Cookie 粘贴到这里保存</div>'
        + '</div>';
    contentDiv.innerHTML += cookieHtml;
}

// ====== 回退渲染 ======
function renderFromLoginMethods(methods) {
    const mainMethods = methods.filter(function(m) { return m.method !== 'cookie'; });
    if (!mainMethods || mainMethods.length === 0) {
        let fields = [];
        try {
            var plat = _loginPlatform;
            for (var i = 0; i < _platformSearchData.length; i++) {
                if (_platformSearchData[i].name === plat) {
                    fields = _platformSearchData[i].config_fields || [];
                    break;
                }
            }
        } catch(e) {}
        renderConfigFields(fields);
        return;
    }
    renderLoginTabs(mainMethods);
    if (mainMethods.length > 0) {
        selectLoginMethod(mainMethods[0].method, methods);
    }
}

// ====== 渲染 Tab (New Capability) ======
function renderLoginCapabilityTabs(methods, note) {
    const tabsDiv = document.getElementById('loginMethodTabs');
    const contentDiv = document.getElementById('loginMethodContent');

    const mainMethods = methods.filter(function(m) { return m.method !== 'cookie'; });

    if (mainMethods.length === 0) {
        tabsDiv.innerHTML = '';
        contentDiv.innerHTML = '<div style="padding:12px;color:#888;font-size:13px;">💡 该平台暂支持 Cookie 粘贴方式（调试模式）</div>';
        document.getElementById('btnStartLogin').style.display = 'none';
        document.getElementById('btnCaptchaLogin').style.display = 'none';
        document.getElementById('btnRefreshScreenshot').style.display = 'none';
        document.getElementById('loginScreenshotArea').style.display = 'none';
        return;
    }

    var html = '';
    mainMethods.forEach(function(m, idx) {
        var icon = getMethodIcon(m.method);
        var active = idx === 0 ? ' style="background:#4361ee;color:#fff;border-color:#4361ee;"' : '';
        html += '<div class="login-method-tab" data-method="' + m.method + '"' + active +
            ' onclick="selectCapabilityLoginMethod(\'' + m.method + '\', null)" style="cursor:pointer;padding:6px 14px;border:1px solid #ddd;border-radius:6px;font-size:13px;display:flex;align-items:center;gap:4px;background:#f5f5f5;">' +
            icon + ' ' + escapeHtml(m.label) + '</div>';
    });
    tabsDiv.innerHTML = html;

    if (note) {
        var noteDiv = document.createElement('div');
        noteDiv.style.cssText = 'font-size:11px;color:#888;margin-bottom:6px;padding:6px 10px;background:#f0f4ff;border-radius:6px;';
        noteDiv.textContent = '🔍 ' + note;
        contentDiv.parentNode.insertBefore(noteDiv, tabsDiv.nextSibling);
    }
}

function getMethodIcon(method) {
    var icons = {
        'password': '🔑',
        'qrcode': '📱',
        'phone': '📞',
        'oauth': '🔗',
        'cookie': '🍪',
        'wechat': '💬',
        'app': '📲',
        // Note: 图标映射应由后端 API /api/platforms/metadata 驱动
        // 此 JS 中的映射作为前端渲染回退（减少 API 调用）
    };
    return icons[method] || '🔑';
}

// ====== Site URL auto-fill ======
function autoFillSiteUrl(url) {
    var input = document.querySelector('input[name="cfg_site_url"]');
    if (input && url && !input.value) {
        input.value = url;
    }
}

// ====== OAuth Provider 按钮渲染 ======
function renderOAuthProviders(providers) {
    var html = '<div style="margin-bottom:10px;">';
    html += '<label style="font-size:12px;color:#666;display:block;margin-bottom:6px;">🔗 第三方登录方式</label>';
    html += '<div style="display:flex;gap:6px;flex-wrap:wrap;">';
    providers.forEach(function(prov) {
        var pid = typeof prov === 'string' ? prov : (prov.id || '');
        var label = typeof prov === 'string' ? prov : (prov.label || pid);
        var icon = typeof prov === 'string' ? getOAuthIcon(prov) : (prov.icon || '🔗');
        html += '<div class="oauth-provider-btn" data-provider="' + escapeHtml(pid) + '" onclick="onSelectOAuthProvider(\'' + escapeHtml(pid) + '\')" style="padding:6px 14px;background:#f0f4ff;border:1px solid #d0d5f0;border-radius:8px;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:6px;transition:all .15s;user-select:none;" onmouseover="this.style.background=\'#e0e7ff\'" onmouseout="this.style.background=\'#f0f4ff\'">';
        html += '<span style="font-size:18px;">' + icon + '</span>';
        html += '<span>' + escapeHtml(label) + '</span>';
        html += '</div>';
    });
    html += '</div></div>';
    return html;
}

function getOAuthIcon(providerId) {
    var icons = {
        'qq': '🐧', 'weibo': '📣', 'wechat_oauth': '💬',
        'github': '🐙', 'google': '🔵', 'apple': '🍎',
        'alipay': '🔶', 'taobao': '🛒',
    };
    return icons[providerId] || '🔗';
}

function onSelectOAuthProvider(providerId) {
    _loginOAuthProvider = providerId;
    document.querySelectorAll('.oauth-provider-btn').forEach(function(btn) {
        if (btn.dataset.provider === providerId) {
            btn.style.background = '#4361ee';
            btn.style.color = '#fff';
            btn.style.borderColor = '#4361ee';
        } else {
            btn.style.background = '#f0f4ff';
            btn.style.color = '#333';
            btn.style.borderColor = '#d0d5f0';
        }
    });
}

function selectCapabilityLoginMethod(method, methods) {
    _loginMethod = method;
    document.querySelectorAll('.login-method-tab').forEach(function(tab) {
        if (tab.dataset.method === method) {
            tab.style.background = '#4361ee';
            tab.style.color = '#fff';
            tab.style.borderColor = '#4361ee';
        } else {
            tab.style.background = '#f5f5f5';
            tab.style.color = '#333';
            tab.style.borderColor = '#ddd';
        }
    });

    if (!methods) {
        fetch('/api/platform/' + _loginPlatform + '/login-capabilities')
        .then(safeJson)
        .then(function(data) {
            _loginGuide = data.guide || null;
            _loginCapData = data;
            if (data.success) {
                renderCapabilityFields(method, data.login_methods || []);
                // Auto-fill site_url when switching tabs
                if (data.site_url_default) {
                    autoFillSiteUrl(data.site_url_default);
                }
            }
        })
        .catch(function() {});
        return;
    }

    renderCapabilityFields(method, methods);
}

function renderCapabilityFields(method, allMethods) {
    var methodDef = null;
    for (var i = 0; i < allMethods.length; i++) {
        if (allMethods[i].method === method) {
            methodDef = allMethods[i];
            break;
        }
    }

    var platform = _loginPlatform;
    var descDiv = document.getElementById('loginMethodContent');
    var preset = _presetsData[platform];
    var html = '';

    showLoginMethodDemo(method);

    // 渲染引导卡片（如 Twitter API 凭证申请指南）
    if (_loginGuide) {
        var g = _loginGuide;
        html += '<div class="guide-banner">';
        html += '<div class="guide-header">📖 ' + escapeHtml(g.title) + '</div>';
        html += '<div class="guide-steps"><ol>';
        g.steps.forEach(function(s) {
            html += '<li>' + escapeHtml(s) + '</li>';
        });
        html += '</ol></div>';
        var btnLabel = g.btn_label || '前往 ' + g.title + ' →';
        if (g.url) {
            html += '<a href="' + escapeHtml(g.url) + '" target="_blank" class="guide-btn">' + btnLabel + '</a>';
        }
        if (g.fields_map) {
            html += '<table class="guide-fields-map"><thead><tr><th>凭证字段</th><th>对应位置</th></tr></thead><tbody>';
            for (var key in g.fields_map) {
                html += '<tr><td><code>' + escapeHtml(key) + '</code></td><td>' + escapeHtml(g.fields_map[key]) + '</td></tr>';
            }
            html += '</tbody></table>';
        }
        html += '</div>';
    }

    if (methodDef && methodDef.description) {
        html += '<div style="font-size:12px;color:#888;margin-bottom:10px;line-height:1.5;">💡 ' +
            escapeHtml(methodDef.description) + '</div>';
    }

    if (method === 'oauth' && methodDef && methodDef.providers && methodDef.providers.length > 0) {
        html += renderOAuthProviders(methodDef.providers);
    }

    if (method === 'qrcode' && methodDef && methodDef.sub_types && methodDef.sub_types.length > 0) {
        html += '<div style="margin-bottom:10px;">';
        html += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">📱 扫码方式</label>';
        html += '<div style="display:flex;gap:6px;flex-wrap:wrap;">';
        var st = methodDef.sub_types;
        for (var si = 0; si < st.length; si++) {
            var subType = st[si];
            var stIcon = subType.id === 'wechat' ? '💬' : (subType.id === 'app' ? '📲' : '📱');
            html += '<span style="padding:4px 10px;background:#f0fff4;border:1px solid #bbf7d0;border-radius:6px;font-size:12px;">' + stIcon + ' ' + escapeHtml(subType.label) + '</span>';
        }
        html += '</div></div>';
    }

    var fieldsToRender = getFieldsForMethod(platform, method, methodDef);

    var hasSiteUrlField = fieldsToRender.indexOf('site_url') >= 0;
    if (preset && preset.sites && preset.sites.length > 0 && hasSiteUrlField) {
        html += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">📌 知名站点（点击自动填充）</label>' +
            '<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px;">';
        preset.sites.forEach(function(s) {
            html += '<button type="button" class="btn btn-sm btn-outline" style="font-size:11px;border:1px solid #ddd;border-radius:4px;padding:3px 8px;background:#f5f5f5;cursor:pointer;"' +
                ' onclick="fillPreset(\'' + escapeHtml(s.name) + '\', \'' + escapeHtml(s.url || '') + '\', \'' + escapeHtml(s.desc || '') + '\')"' +
                ' title="' + escapeHtml(s.desc || '') + '">' +
                escapeHtml(s.name || '') + '</button>';
        });
        html += '</div>';
    }

    fieldsToRender.forEach(function(fkey) {
        if (fkey === 'site_url') {
            var val = '';
            if (_loginCapData && _loginCapData.site_url_default) {
                val = _loginCapData.site_url_default;
            } else if (preset && preset.sites && preset.sites.length > 0) {
                val = preset.sites[0].url || '';
            }
            html += '<div class="form-group"><label>平台地址</label>' +
                '<input type="text" name="cfg_site_url" placeholder="https://..."' +
                (val ? ' value="' + val + '"' : '') +
                ' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        } else if (fkey === 'username') {
            html += '<div class="form-group"><label>用户名/邮箱</label>' +
                '<input type="text" name="cfg_username" placeholder="登录用户名或邮箱"' +
                ' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        } else if (fkey === 'password') {
            html += '<div class="form-group"><label>密码</label>' +
                '<input type="password" name="cfg_password" placeholder="登录密码"' +
                ' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        } else if (fkey === 'phone') {
            html += '<div class="form-group"><label>手机号码</label>' +
                '<input type="text" name="cfg_phone" placeholder="手机号码"' +
                ' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        } else if (fkey === 'cookie') {
            html += '<div class="form-group"><label>Cookie <span style="color:#999;font-size:12px;">（从浏览器 F12 复制）</span></label>' +
                '<textarea name="cfg_cookie" rows="3" placeholder="粘贴完整的 Cookie 字符串"' +
                ' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-family:monospace;font-size:11px;"></textarea></div>';
        } else {
            html += '<div class="form-group"><label>' + escapeHtml(fkey) + '</label>' +
                '<input type="text" name="cfg_' + fkey + '"' +
                ' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        }
    });

    descDiv.innerHTML = html;

    // Show captcha info banner if platform has captcha
    if (_loginCapData && _loginCapData.captcha_info && _loginCapData.captcha_info.has_captcha) {
        var existingBanner = document.getElementById('captchaInfoBanner');
        if (!existingBanner) {
            var banner = document.createElement('div');
            banner.id = 'captchaInfoBanner';
            banner.style.cssText = 'margin-top:10px;padding:10px 12px;background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;font-size:12px;';
            var noteText = _loginCapData.captcha_info.note || '该平台有验证码保护，登录时需手动处理验证码';
            banner.innerHTML = '🔐 <strong>验证码提示：</strong>' + escapeHtml(noteText);
            descDiv.parentNode.appendChild(banner);
        }
    } else {
        var oldBanner = document.getElementById('captchaInfoBanner');
        if (oldBanner) oldBanner.remove();
    }

    var btnStart = document.getElementById('btnStartLogin');
    var btnCaptcha = document.getElementById('btnCaptchaLogin');
    var btnRefresh = document.getElementById('btnRefreshScreenshot');
    var screenshotArea = document.getElementById('loginScreenshotArea');
    var btnSaveOnly = document.getElementById('btnSaveOnly');

    if (method === 'password') {
        btnStart.style.display = 'inline-block';
        btnStart.textContent = '🚀 开始浏览器登录';
        btnStart.disabled = false;
        btnCaptcha.style.display = 'none';
        btnRefresh.style.display = 'none';
        screenshotArea.style.display = 'none';
    } else if (method === 'qrcode') {
        btnStart.style.display = 'inline-block';
        btnStart.textContent = '📱 打开扫码登录页';
        btnStart.disabled = false;
        btnCaptcha.style.display = 'none';
        btnRefresh.style.display = 'none';
        screenshotArea.style.display = 'none';
    } else if (method === 'phone') {
        btnStart.style.display = 'inline-block';
        btnStart.textContent = '📱 发送验证码';
        btnStart.disabled = false;
        btnCaptcha.style.display = 'none';
        btnRefresh.style.display = 'none';
        screenshotArea.style.display = 'none';
    } else {
        btnStart.style.display = 'none';
        btnCaptcha.style.display = 'none';
        btnRefresh.style.display = 'none';
        screenshotArea.style.display = 'none';
    }
    document.getElementById('loginStatusMsg').style.display = 'none';
    _isLoginRunning = false;

    // 测试连接按钮
    var btnTestConn = document.getElementById('btnTestConnectionAdd');
    if (method === 'cookie' || method === 'oauth1' || method === 'bearer' || method === 'password') {
        btnTestConn.style.display = 'inline-block';
    } else {
        btnTestConn.style.display = 'none';
    }
}

function getFieldsForMethod(platform, method, methodDef) {
    if (methodDef && methodDef.fields && methodDef.fields.length > 0) {
        var fields = methodDef.fields.slice();  // 复制，避免修改原数组
        // 如果 API 有 site_url_default 但 fields 没包含 site_url，自动加上
        if (_loginCapData && _loginCapData.site_url_default && fields.indexOf('site_url') < 0) {
            fields.unshift('site_url');
        }
        return fields;
    }
    var preset = _presetsData[platform];
    var fields = [];
    if ((_loginCapData && _loginCapData.site_url_default) || (preset && preset.sites && preset.sites.length > 0)) {
        fields.push('site_url');
    }
    if (method === 'password') {
        fields.push('username');
        fields.push('password');
    } else if (method === 'phone') {
        fields.push('phone');
    } else if (method === 'qrcode') {
    } else if (method === 'oauth') {
    } else if (method === 'cookie') {
        fields.push('cookie');
    }
    return fields;
}

// ====== 渲染 Tab (Old Style) ======
function renderLoginTabs(methods) {
    const tabsDiv = document.getElementById('loginMethodTabs');
    let html = '';
    methods.forEach(function(m, idx) {
        const icon = m.icon || '🔑';
        const active = idx === 0 ? ' style="background:#4361ee;color:#fff;border-color:#4361ee;"' : '';
        html += '<div class="login-method-tab" data-method="' + m.method + '"' + active +
            ' onclick="selectLoginMethod(\'' + m.method + '\', null)" style="cursor:pointer;padding:6px 14px;border:1px solid #ddd;border-radius:6px;font-size:13px;display:flex;align-items:center;gap:4px;background:#f5f5f5;">' +
            icon + ' ' + escapeHtml(m.label) + '</div>';
    });
    tabsDiv.innerHTML = html;
}

// ====== DOM 加载完成初始化 ======
document.addEventListener('DOMContentLoaded', function() {
    fetch('/api/platforms/presets')
    .then(safeJson)
    .then(data => {
        if (data.success) _presetsData = data.presets || {};
    })
    .catch(() => {});
    setTimeout(refreshAllStatuses, 2000);
    setInterval(refreshAllStatuses, 120000);
    startTimeAutoUpdater();
    // 初始化过滤统计
    setTimeout(filterAccounts, 100);
});
