function _selectScanMethod(siteUrl, aid, btn) {
    // 防重入：最多重试2次
    _scanMethodRetryCount++;
    if (_scanMethodRetryCount > 2) {
        showLoginStatus('error', '❌ 获取扫码方式失败，请尝试其他登录方式');
        btn.disabled = false;
        btn.textContent = '📱 打开扫码登录页';
        _isLoginRunning = false;
        return;
    }
    // 获取该平台支持的扫码方式
    showLoginStatus('info', '⏳ 正在获取扫码方式...');
    btn.disabled = true;
    btn.textContent = '⏳ 查询中...';

    fetch('/api/login/scan-methods/' + _loginPlatform)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success || !data.methods || data.methods.length === 0) {
            // 没有多方式或平台无扫码能力，直接显示错误
            var msg = data.error || '该平台暂不支持扫码登录';
            // 检查探索数据是否显示有扫码
            if (_loginCapData) {
                var hasQr = false;
                var methods = _loginCapData.login_methods || [];
                for (var i = 0; i < methods.length; i++) {
                    if (methods[i].method === 'qrcode' && methods[i].detected) {
                        hasQr = true;
                        break;
                    }
                }
                if (hasQr) {
                    msg = '该平台虽然有扫码能力，但当前页面未检测到二维码元素，可能需要在特定页面扫码';
                }
            }
            showLoginStatus('warning', '❌ ' + msg);
            btn.disabled = false;
            btn.textContent = '📱 重试';
            _isLoginRunning = false;
            _scanMethodRetryCount = 0;
            return;
        }

        // 显示扫码方式供用户选择
        var methodList = data.methods;
        // 如果只有一个方式，直接使用
        if (methodList.length === 1) {
            _doPickScanMethod(methodList[0].id, null);
            return;
        }

        // 多个方式，显示选择区域
        var html = '<div style="margin:8px 0;"><strong>📱 选择扫码方式：</strong></div><div style="display:flex;gap:6px;flex-wrap:wrap;margin:6px 0;">';
        methodList.forEach(function(m) {
            var label = m.label || m.id;
            var icon = m.icon || '📱';
            html += '<button onclick="_doPickScanMethod(\'' + m.id + '\', this)" style="padding:6px 12px;border:1px solid #a5d6a7;border-radius:6px;background:#e8f5e9;cursor:pointer;font-size:13px;">' + icon + ' ' + label + '</button>';
        });
        html += '</div>';
        var infoDiv = document.getElementById('qrScanInfo');
        infoDiv.innerHTML = html;
        infoDiv.style.display = 'block';
        btn.textContent = '📱 选择扫码方式';
        _isLoginRunning = false;
        _scanMethodRetryCount = 0;
    })
    .catch(function(e) {
        showLoginStatus('error', '❌ 获取扫码方式失败: ' + e.message);
        btn.disabled = false;
        btn.textContent = '📱 重试';
        _isLoginRunning = false;
    });
}

function _doPickScanMethod(methodId, btnEl) {
    _selectedScanMethod = methodId;
    if (btnEl) {
        if (btnEl.parentNode) {
            var p = btnEl.parentNode;
            p.querySelectorAll('button').forEach(function(b) {
                b.style.borderColor = '#a5d6a7';
                b.style.background = '#e8f5e9';
            });
        }
        btnEl.style.borderColor = '#2e7d32';
        btnEl.style.background = '#c8e6c9';
    }
    document.getElementById('btnStartLogin').textContent = '📱 打开扫码登录页';
    document.getElementById('qrScanInfo').style.display = 'none';
    startQrCodeLogin();
}

function startQrCodePolling() {
    if (_qrPollTimer) clearInterval(_qrPollTimer);
    var pollCount = 0;
    _qrPollTimer = setInterval(function() {
        pollCount++;
        if (pollCount > 30 || !_qrSessionId) {
            clearInterval(_qrPollTimer);
            _qrPollTimer = null;
            if (_qrSessionId) {
                showLoginStatus('warning', '⏰ 轮询超时，请点击「刷新截图」重新查看状态');
            }
            return;
        }
        fetch('/api/login/qrcode/' + _loginPlatform + '/poll/' + _qrSessionId)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) {
                if (data.status === 'expired' || data.status === 'closed') {
                    clearInterval(_qrPollTimer);
                    _qrPollTimer = null;
                    showLoginStatus('error', '❌ 会话已过期');
                }
                return;
            }
            if (data.logged_in && data.cookies) {
                clearInterval(_qrPollTimer);
                _qrPollTimer = null;
                _isLoginRunning = false;
                setFieldValue('cfg_cookie', data.cookies);
                _loginResultCookie = data.cookies;
                showLoginStatus('info', '⏳ Cookie已获取，正在校验...');
                document.getElementById('btnStartLogin').textContent = '✅ 已登录';
                document.getElementById('btnStartLogin').disabled = true;
                doVerifyAndEnableConfirm(data.cookies, 0);
            } else if (data.status === 'cookie_unverified') {
                // Cookie 已检测到但验证未通过 — 展示给用户确认
                setFieldValue('cfg_cookie', data.cookies || '');
                showLoginStatus('warning', '⚠️ ' + (data.message || 'Cookie 验证未通过，请确认是否已登录'));
                document.getElementById('btnStartLogin').textContent = '📋 Cookie已获取，点击保存';
                document.getElementById('btnStartLogin').disabled = false;
                _isLoginRunning = false;
                clearInterval(_qrPollTimer);
                _qrPollTimer = null;
            } else if (data.needs_captcha && data.image) {
                showCaptchaInput(data.image, true);
                showCaptchaFeedback('需要新验证码', true);
                showLoginStatus('warning', '🔒 需要新验证码');
                document.getElementById('btnSubmitCaptcha').disabled = false;
                document.getElementById('btnSubmitCaptcha').textContent = '✅ 提交验证码';
            } else if (data.running) {
                // 仍在进行中，继续等待
            } else if (data.message) {
                showLoginStatus('info', '🔄 ' + data.message);
            }
        })
        .catch(function() {});
    }, 2000);
}

function toggleDebugCookie() {
    var area = document.getElementById('debugCookieArea');
    var toggle = document.getElementById('debugCookieToggle');
    if (area.style.display === 'none' || area.style.display === '') {
        area.style.display = 'block';
        toggle.textContent = '🔧 关闭调试';
        toggle.style.color = '#996600';
    } else {
        area.style.display = 'none';
        toggle.textContent = '🔧 调试';
        toggle.style.color = '#888';
    }
}

function onEditAccount(aid) {
    fetch('/api/accounts/' + aid)
    .then(function(r) { return r.json(); })
    .then(function(cfg) {
        if (!cfg || cfg.error) {
            alert('获取账号信息失败: ' + (cfg ? cfg.error : '未知错误'));
            return;
        }
        var platform = cfg.platform || '';
        if (!platform) {
            alert('账号没有平台信息');
            return;
        }
        _loginPlatform = platform;
        _loginMethod = 'cookie';
        _loginSession = null;
        _isLoginRunning = false;

        // 从缓存中查找平台显示名
        var displayName = platform;
        for (var i = 0; i < _platformSearchData.length; i++) {
            if (_platformSearchData[i].name === platform) {
                displayName = _platformSearchData[i].display_name;
                _platformSearchData[i].config_fields = _platformSearchData[i].config_fields || [];
                break;
            }
        }
        document.getElementById('addPlatInput').value = platform;
        if (displayName) {
            document.getElementById('addPlatName').textContent = displayName;
        }
        document.getElementById('editAccountId').value = aid;
        document.getElementById('debugCookieArea').style.display = 'none';
        document.getElementById('addFormTitle').innerHTML = '✏️ 编辑账号 — <span>' + escapeHtml(cfg._accountName || '') + '</span>';

        // 获取登录能力
        fetch('/api/platform/' + platform + '/login-capabilities')
        .then(function(r) { return r.json(); })
        .then(function(capData) {
            if (capData.success && capData.login_methods && capData.login_methods.length > 0) {
                var methods = capData.login_methods;
                renderLoginCapabilityTabs(methods, capData.note || '');
                var preferredMethod = 'cookie';
                if (cfg.username && cfg.password) {
                    preferredMethod = 'password';
                } else if (cfg.phone) {
                    preferredMethod = 'phone';
                }
                var available = methods.filter(function(m) { return m.method !== 'cookie'; });
                var hasPreferred = available.some(function(m) { return m.method === preferredMethod; });
                var defaultMethod = hasPreferred ? preferredMethod : (available.length > 0 ? available[0].method : 'cookie');
                selectCapabilityLoginMethod(defaultMethod, methods);
            } else {
                var methods = [];
                try {
                    var plat = platform;
                    for (var i = 0; i < _platformSearchData.length; i++) {
                        if (_platformSearchData[i].name === plat) {
                            methods = _platformSearchData[i].login_methods || [];
                            break;
                        }
                    }
                } catch(e) {}
                renderFromLoginMethods(methods);
            }

            document.getElementById('addFormTitle').innerHTML = '✏️ 编辑账号 — <span>' + escapeHtml(cfg._accountName || '') + '</span>';
            document.getElementById('addAccountName').value = cfg._accountName || '';
            document.getElementById('btnSaveOnly').textContent = '💾 更新';

            Object.keys(cfg).forEach(function(k) {
                if (k.startsWith('_')) return;
                var input = document.querySelector('input[name="cfg_' + k + '"], textarea[name="cfg_' + k + '"]');
                if (input) input.value = cfg[k] || '';
            });

            document.getElementById('addFormBox').style.display = 'flex';
        })
        .catch(function() {
            onAddAccount();
            document.getElementById('addFormTitle').innerHTML = '✏️ 编辑账号 — <span>' + escapeHtml(cfg._accountName || '') + '</span>';
            document.getElementById('editAccountId').value = aid;
            document.getElementById('addAccountName').value = cfg._accountName || '';
            document.getElementById('btnSaveOnly').textContent = '💾 更新';
            Object.keys(cfg).forEach(function(k) {
                if (k.startsWith('_')) return;
                var input = document.querySelector('input[name="cfg_' + k + '"], textarea[name="cfg_' + k + '"]');
                if (input) input.value = cfg[k] || '';
            });
            document.getElementById('addFormBox').style.display = 'flex';
        });
    })
    .catch(function(e) { alert('请求失败: ' + e.message); });
}

var _origFormTitle = '➕ 添加账号 — ';
var _loginReadyToSave = false;  // 登录成功 + Cookie校验通过后设为true，允许「确认添加」
var _loginResultCookie = '';   // 登录成功后的cookie，暂存等待确认

// ====== 统一浏览器登录 + 验证码 + 扫码 + 轮询 ======

// ====== 统一浏览器登录 ======
function unifiedLoginStart() {
    if (_isLoginRunning) return; _isLoginRunning = true;
    if (_loginMethod === 'qrcode') { startQrCodeLogin(); return; }
    if (_loginMethod === 'phone') {
        var aid = parseInt(document.getElementById('editAccountId').value) || 0, phone = getFieldValue('cfg_phone'), siteUrl = getFieldValue('cfg_site_url');
        if (!phone) { showLoginStatus('error', '请输入手机号码'); _isLoginRunning = false; return; }
        showLoginStatus('info', '⏳ 正在打开登录页并发送验证码...');
        var btn = document.getElementById('btnStartLogin'); btn.disabled = true; btn.textContent = '⏳ 发送中...';
        fetch('/api/platform/'+_loginPlatform+'/login/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:aid,method:'phone',phone:phone,site_url:siteUrl})}).then(function(r){return r.json()}).then(function(data){
            if (data.logged_in && data.cookies) { setFieldValue('cfg_cookie',data.cookies);_loginResultCookie=data.cookies;showLoginStatus('info','⏳ Cookie已获取，正在校验...');doVerifyAndEnableConfirm(data.cookies,aid); }
            else if (data.needs_captcha && data.image) { showLoginScreenshot(data.image); showLoginStatus('warning','📱 验证码已发送，请输入验证码后点击「提交验证码」'); document.getElementById('btnCaptchaLogin').style.display='inline-block'; document.getElementById('btnCaptchaLogin').textContent='📱 提交验证码'; document.getElementById('btnRefreshScreenshot').style.display='inline-block'; }
            else { showLoginStatus('error','❌ '+(data.error||'操作失败')); btn.disabled=false; btn.textContent='📱 发送验证码'; _isLoginRunning=false; }
        }).catch(function(e){showLoginStatus('error','❌ 网络错误: '+e.message);btn.disabled=false;btn.textContent='📱 发送验证码';_isLoginRunning=false;});
        return;
    }
    var aid=parseInt(document.getElementById('editAccountId').value)||0,username=getFieldValue('cfg_username'),password=getFieldValue('cfg_password'),siteUrl=getFieldValue('cfg_site_url');
    if (!username||!password){showLoginStatus('error','请输入用户名和密码');_isLoginRunning=false;return;}
    hideCaptchaInput();resetProgressBar();setStepActive(1,'启动浏览器并打开登录页...');showLoginStatus('info','⏳ 正在启动浏览器登录...');
    var btn=document.getElementById('btnStartLogin');btn.disabled=true;btn.textContent='⏳ 启动中...';
    fetch('/api/platform/'+_loginPlatform+'/login/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:aid,username:username,password:password,site_url:siteUrl})}).then(function(r){return r.json()}).then(function(data){
        if(data.logged_in&&data.cookies){setStepDone(1,'登录页已打开');setStepDone(2,'已填写账号密码');setStepDone(3,'无需验证码');setStepDone(4,'无需验证码');setStepActive(5,'Cookie校验中...');setFieldValue('cfg_cookie',data.cookies);_loginResultCookie=data.cookies;showLoginStatus('info','⏳ Cookie已获取，正在校验...');doVerifyAndEnableConfirm(data.cookies,aid);}
        else if(data.needs_captcha&&data.image){setStepDone(1,'登录页已打开');setStepDone(2,'已填写账号密码');setStepDone(3,'检测到验证码');showCaptchaInput(data.image,data.captcha_type==='checkbox'||data.captcha_type==='text');var msg='🔒 需要验证码';if(data.captcha_type==='text')msg='🔢 请输入图片中的验证码';else if(data.captcha_type==='checkbox')msg='☑️ 请处理复选框验证码';else if(data.captcha_type==='recaptcha')msg='🔒 Google reCAPTCHA';showLoginStatus('warning',msg);}
        else if(data.success&&data.needs_captcha){setStepDone(1,'登录页已打开');setStepDone(2,'已填写账号密码');setStepDone(3,'检测到验证码');showCaptchaInput(data.image||'',true);showLoginStatus('warning','🔒 需要验证码处理');}
        else{setStepFailed(3,data.error||'登录失败');showLoginStatus('error','❌ '+(data.error||'登录失败'));btn.disabled=false;btn.textContent='🚀 开始浏览器登录';_isLoginRunning=false;}
    }).catch(function(e){setStepFailed(1,'网络错误: '+e.message);showLoginStatus('error','❌ 网络错误: '+e.message);btn.disabled=false;btn.textContent='🚀 开始浏览器登录';_isLoginRunning=false;});
}
function unifiedLoginCaptcha() {
    var btn = document.getElementById('btnCaptchaLogin');btn.disabled=true;btn.textContent='⏳ 处理中...';showLoginStatus('info','⏳ 正在点击验证码并提交登录...');
    var aid = parseInt(document.getElementById('editAccountId').value)||0;
    fetch('/api/platform/'+_loginPlatform+'/login/captcha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:aid})}).then(function(r){return r.json()}).then(function(data){
        if(data.logged_in&&data.cookies){setFieldValue('cfg_cookie',data.cookies);_loginResultCookie=data.cookies;showLoginStatus('info','⏳ Cookie已获取，正在校验...');btn.disabled=true;doVerifyAndEnableConfirm(data.cookies,aid);}
        else if(data.needs_captcha&&data.image){showCaptchaInput(data.image,data.captcha_type==='checkbox');showLoginStatus('warning','🔒 请输入验证码');btn.disabled=false;btn.textContent='✅ 点验证码并登录';}
        else if(data.image){showLoginScreenshot(data.image);showLoginStatus('warning',data.message||'🔒 请重试');btn.disabled=false;btn.textContent='✅ 点验证码并登录';}
        else{showLoginStatus('error','❌ '+(data.error||'验证码处理失败'));btn.disabled=false;btn.textContent='✅ 点验证码并登录';}
    }).catch(function(e){showLoginStatus('error','❌ 网络错误: '+e.message);btn.disabled=false;btn.textContent='✅ 点验证码并登录';});
}
function unifiedSubmitCaptcha() {
    var code = document.getElementById('captchaCodeInput').value.trim();
    if(!code){showCaptchaFeedback('请输入验证码',true);return;}
    var btn=document.getElementById('btnSubmitCaptcha');btn.disabled=true;btn.textContent='⏳ 提交中...';showCaptchaFeedback('正在提交验证码...',false);
    var aid=parseInt(document.getElementById('editAccountId').value)||0;setStepActive(5,'提交验证码核验中...');
    fetch('/api/platform/'+_loginPlatform+'/login/submit_captcha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:aid,captcha_code:code})}).then(function(r){return r.json()}).then(function(data){
        if(data.logged_in&&data.cookies){setStepDone(4,'验证码通过');setStepActive(5,'Cookie校验中...');setFieldValue('cfg_cookie',data.cookies);_loginResultCookie=data.cookies;showLoginStatus('info','⏳ Cookie已获取，正在校验...');hideCaptchaInput();doVerifyAndEnableConfirm(data.cookies,aid);}
        else if(data.needs_captcha&&data.image){setStepActive(3,'需要新验证码');showCaptchaInput(data.image,true);showCaptchaFeedback((data.error||'验证码错误')+'，请重新输入',true);showLoginStatus('warning','🔒 '+(data.error||'验证码错误，请重试'));btn.disabled=false;btn.textContent='✅ 提交验证码';}
        else if(data.captcha_verified&&!data.logged_in){setStepDone(4,'验证码核验通过 ✓，等待登录...');setStepActive(5,'登录提交中...');showCaptchaFeedback('✅ 验证码通过，正在登录...',false);showLoginStatus('info','⏳ 验证码通过，正在自动登录...');btn.textContent='⏳ 登录中...';setTimeout(function(){unifiedPollLoginResult(aid)},2000);}
        else{setStepFailed(5,data.error||'验证码处理失败');showCaptchaFeedback(data.error||'处理失败',true);showLoginStatus('error','❌ '+(data.error||'验证码处理失败'));btn.disabled=false;btn.textContent='✅ 提交验证码';}
    }).catch(function(e){setStepFailed(5,'网络错误: '+e.message);showCaptchaFeedback('网络错误',true);showLoginStatus('error','❌ 网络错误: '+e.message);btn.disabled=false;btn.textContent='✅ 提交验证码';});
}
function unifiedPollLoginResult(aid) {
    fetch('/api/platform/'+_loginPlatform+'/login/poll_result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:aid})}).then(function(r){return r.json()}).then(function(data){
        if(data.logged_in&&data.cookies){setStepDone(4,'验证码通过');setStepActive(5,'Cookie校验中...');setFieldValue('cfg_cookie',data.cookies);_loginResultCookie=data.cookies;showLoginStatus('info','⏳ Cookie已获取，正在校验...');hideCaptchaInput();doVerifyAndEnableConfirm(data.cookies,aid);}
        else if(data.needs_captcha&&data.image){showCaptchaInput(data.image,true);showCaptchaFeedback('需要新验证码',true);showLoginStatus('warning','🔒 需要新验证码');document.getElementById('btnSubmitCaptcha').disabled=false;document.getElementById('btnSubmitCaptcha').textContent='✅ 提交验证码';}
        else if(data.running){setTimeout(function(){unifiedPollLoginResult(aid)},2000);}
        else{setStepFailed(5,data.error||'登录超时');showCaptchaFeedback(data.error||'登录超时',true);document.getElementById('btnSubmitCaptcha').disabled=false;document.getElementById('btnSubmitCaptcha').textContent='✅ 提交验证码';}
    }).catch(function(){setTimeout(function(){unifiedPollLoginResult(aid)},3000);});
}
function unifiedRefreshCaptcha() {
    document.getElementById('btnRefreshCaptcha').disabled=true;document.getElementById('btnRefreshCaptcha').textContent='⏳ 刷新中...';showCaptchaFeedback('正在获取新验证码...',false);
    fetch('/api/platform/'+_loginPlatform+'/login/refresh_captcha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:parseInt(document.getElementById('editAccountId').value)||0})}).then(function(r){return r.json()}).then(function(data){
        if(data.success&&data.image){document.getElementById('captchaImage').src='data:image/png;base64,'+data.image;document.getElementById('loginScreenshotImg').src='data:image/png;base64,'+data.image;document.getElementById('captchaCodeInput').value='';showCaptchaFeedback('新验证码已获取',false);}
        else{showCaptchaFeedback(data.error||'刷新失败',true);}
        document.getElementById('btnRefreshCaptcha').disabled=false;document.getElementById('btnRefreshCaptcha').textContent='🔄 换一张';
    }).catch(function(e){showCaptchaFeedback('网络错误',true);document.getElementById('btnRefreshCaptcha').disabled=false;document.getElementById('btnRefreshCaptcha').textContent='🔄 换一张';});
}
function unifiedAutoCaptcha() {
    var btn=document.getElementById('btnAutoCaptcha');btn.disabled=true;btn.textContent='⏳ 识别中...';showCaptchaFeedback('正在自动识别验证码...',false);
    fetch('/api/platform/'+_loginPlatform+'/login/auto_captcha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:parseInt(document.getElementById('editAccountId').value)||0})}).then(function(r){return r.json()}).then(function(data){
        if(data.success&&data.code){document.getElementById('captchaCodeInput').value=data.code;showCaptchaFeedback('识别结果: '+data.code+'，点击「提交验证码」',false);unifiedSubmitCaptcha();}
        else{showCaptchaFeedback(data.error||'识别失败，请手动输入',true);}
        btn.disabled=false;btn.textContent='🤖 自动识别';
    }).catch(function(){showCaptchaFeedback('自动识别失败，请手动输入',true);btn.disabled=false;btn.textContent='🤖 自动识别';});
}
// ====== Cookie校验 + 启用确认添加 ======
function doVerifyAndEnableConfirm(cookie, aid) {
    // 使用已有的 /api/accounts/test-connection 校验 Cookie（不保存到DB）
    var siteUrl = getFieldValue('cfg_site_url');
    var username = getFieldValue('cfg_username');
    fetch('/api/accounts/test-connection', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            platform: _loginPlatform,
            config: {cookie: cookie, site_url: siteUrl, username: username}
        })
    }).then(function(r){return r.json()}).then(function(data){
        if (data.logged_in === true) {
            // ✅ Cookie校验通过 — 显示成功，等待用户确认
            setStepDone(5, '✅ ' + (data.status || 'Cookie校验通过'));
            _loginReadyToSave = true;
            _loginResultCookie = cookie;
            var saveBtn = document.getElementById('btnSaveOnly');
            saveBtn.textContent = '✅ 确认添加';
            saveBtn.className = 'btn btn-success';
            saveBtn.style.fontWeight = 'bold';
            saveBtn.style.fontSize = '15px';
            var statusMsg = '✅ Cookie校验通过';
            if (data.username) statusMsg += ' — 用户名: ' + data.username;
            if (data.points) statusMsg += ' (' + (data.points_label||'积分') + ': ' + data.points + ')';
            showLoginStatus('success', statusMsg + '。请点击「确认添加」保存账号');
            document.getElementById('btnStartLogin').disabled = true;
            document.getElementById('btnStartLogin').textContent = '✅ 已登录';
        } else {
            // ❌ Cookie校验失败 — 显示错误但保留Cookie，用户可重试
            setStepFailed(5, (data.status || 'Cookie校验失败'));
            showLoginStatus('error', '❌ Cookie校验失败: ' + (data.status || data.error || '未知错误'));
            _loginReadyToSave = false;
            // 允许用户重试校验
            var retryBtn = document.getElementById('btnStartLogin');
            retryBtn.disabled = false;
            retryBtn.textContent = '🔄 重试验证';
            _isLoginRunning = false;
        }
    }).catch(function(e){
        setStepFailed(5, '校验请求失败: ' + e.message);
        showLoginStatus('error', '❌ Cookie校验请求失败: ' + e.message);
        _isLoginRunning = false;
    });
}
function unifiedRefreshScreenshot() {
    var platform=_loginPlatform;
    if(_loginMethod==='qrcode'&&_qrSessionId){fetch('/api/login/qrcode/'+platform+'/poll/'+_qrSessionId).then(function(r){return r.json()}).then(function(data){if(data.success&&data.image)document.getElementById('loginScreenshotImg').src='data:image/png;base64,'+data.image;if(data.status==='logged_in'&&data.cookies){clearInterval(_qrPollTimer);_qrPollTimer=null;setFieldValue('cfg_cookie',data.cookies);showLoginStatus('success','✅ 登录成功！');}else{showLoginStatus('info','🔄 '+(data.message||'截图已刷新'));}}).catch(function(){});return;}
    fetch('/api/platform/'+platform+'/login/screenshot').then(function(r){return r.json()}).then(function(data){if(data.success&&data.image)document.getElementById('loginScreenshotImg').src='data:image/png;base64,'+data.image}).catch(function(){});
}

// ====== QR码登录 ======
function startQrCodeLogin() {
    _scanMethodRetryCount=0;var siteUrl=getFieldValue('cfg_site_url'),aid=document.getElementById('editAccountId').value,btn=document.getElementById('btnStartLogin');
    if(!_selectedScanMethod){_selectScanMethod(siteUrl,aid,btn);return;}
    document.getElementById('qrScanInfo').style.display='none';
    var countdown=3;btn.disabled=true;btn.textContent='📱 获取二维码中... 3';showLoginStatus('info','⏳ 准备获取二维码...');
    var ct=setInterval(function(){countdown--;if(countdown>0){btn.textContent='📱 获取二维码中... '+countdown;}else{clearInterval(ct);btn.textContent='⏳ 打开中...';showLoginStatus('info','⏳ 正在打开平台登录页...');
    var reqBody={account_id:parseInt(aid)||0,site_url:siteUrl};if(_selectedScanMethod)reqBody.method=_selectedScanMethod;
    fetch('/api/login/qrcode/'+_loginPlatform+'/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(reqBody)}).then(function(r){return r.json()}).then(function(data){
        if(!data.success){var em=data.error||'获取二维码失败';if(data.no_qrcode)showLoginStatus('warning','❌ 未检测到二维码，请尝试其他登录方式（账号密码/Cookie粘贴）');else showLoginStatus('error','❌ '+em+'，点击重试');btn.disabled=false;btn.textContent='📱 点击重试';_isLoginRunning=false;return;}
        _qrSessionId=data.session_id;_loginSession=data.session_id;
        var sa=data.scan_app||'',sh=data.scan_hint||'';
        if(sa){var id=document.getElementById('qrScanInfo');id.innerHTML='📱 请使用 <strong>'+escapeHtml(sa)+'</strong> 扫码';if(sh)id.innerHTML+='<br><span style="font-size:11px;color:#555;">'+escapeHtml(sh)+'</span>';id.style.display='block';}
        if(data.image)showLoginScreenshot(data.image);
        showLoginStatus('info','🔍 '+(data.message||'请在截图页面中扫码/登录'));document.getElementById('btnCaptchaLogin').style.display='none';document.getElementById('btnRefreshScreenshot').style.display='inline-block';btn.textContent='📱 扫码中...';
        startQrCodePolling();
    }).catch(function(e){showLoginStatus('error','❌ 网络错误: '+e.message+'，点击重试');btn.disabled=false;btn.textContent='📱 点击重试';_isLoginRunning=false;});}},1000);
}

// ====== 批量刷新 ======
function batchRefreshAccounts() {
    var btn=document.querySelector('button[onclick*="batchRefresh"]');if(btn){btn.disabled=true;btn.textContent='🔄 刷新中...';}
    showBatchRefreshProgress('start');
    fetch('/api/accounts/batch/refresh',{method:'POST'}).then(function(r){return r.json()}).then(function(data){
        if(data.success){showBatchRefreshProgress('done',data.refreshed+'/'+data.total);refreshAllStatuses(false);setTimeout(function(){if(btn){btn.disabled=false;btn.textContent='🔄 批量刷新';}showBatchRefreshProgress('hide')},3000);}
        else{showBatchRefreshProgress('error',data.error||'未知错误');setTimeout(function(){if(btn){btn.disabled=false;btn.textContent='🔄 批量刷新';}showBatchRefreshProgress('hide')},3000);}
    }).catch(function(e){showBatchRefreshProgress('error',e.message);setTimeout(function(){if(btn){btn.disabled=false;btn.textContent='🔄 批量刷新';}showBatchRefreshProgress('hide')},3000);});
}
function showBatchRefreshProgress(state,msg) {
    var el=document.getElementById('batchRefreshProgress');
    if(!el){el=document.createElement('div');el.id='batchRefreshProgress';el.style.cssText='margin-bottom:10px;border-radius:8px;overflow:hidden;display:none;';var fb=document.querySelector('.filter-bar');if(fb)fb.parentNode.insertBefore(el,fb.nextSibling);}
    if(state==='start'){el.style.display='block';el.innerHTML='<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:#eef2ff;border:1px solid #d0d5f0;border-radius:8px;"><div style="font-size:13px;color:#4361ee;flex-shrink:0;">🔄 批量刷新中...</div><div style="flex:1;height:6px;background:#e0e0e0;border-radius:3px;overflow:hidden;"><div style="width:100%;height:100%;background:linear-gradient(90deg,#4361ee,#7c3aed);border-radius:3px;animation:refreshProgress 1.5s ease-in-out infinite;"></div></div></div><style>@keyframes refreshProgress{0%{width:20%}50%{width:80%}100%{width:20%}}</style>';}
    else if(state==='done'){el.innerHTML='<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;font-size:13px;color:#065f46;">📊 批量预检完成：'+msg+' 个账号（API通过/失效/跳过详情见响应）</div>';}
    else if(state==='error'){el.innerHTML='<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;font-size:13px;color:#991b1b;">❌ 批量刷新失败：'+(msg||'未知错误')+'</div>';}
    else{el.style.display='none';}
}
