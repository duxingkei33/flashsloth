// ====== 工具函数 ======
function getPlatformIconCode(name) { return _platIconsMap[name] || _platIconsMap['default']; }
function getPlatformColor(name) { return _platColorsMap[name] || _platColorsMap['default']; }
function escapeHtml(text) { var d = document.createElement('div'); d.textContent = text || ''; return d.innerHTML; }
function getFieldValue(name) { var el = document.querySelector('input[name="' + name + '"]'); if (!el) el = document.querySelector('textarea[name="' + name + '"]'); return el ? el.value.trim() : ''; }
function setFieldValue(name, value) { var el = document.querySelector('input[name="' + name + '"]'); if (!el) el = document.querySelector('textarea[name="' + name + '"]'); if (el) el.value = value; }
function showLoginStatus(type, msg) {
    var div = document.getElementById('loginStatusMsg'); div.style.display = 'block';
    if (type === 'success') { div.style.background = '#d4edda'; div.style.color = '#155724'; }
    else if (type === 'error') { div.style.background = '#f8d7da'; div.style.color = '#721c24'; }
    else if (type === 'warning') { div.style.background = '#fff3cd'; div.style.color = '#856404'; }
    else { div.style.background = '#d1ecf1'; div.style.color = '#0c5460'; }
    div.innerHTML = msg;
}
function showLoginScreenshot(b64) { document.getElementById('loginScreenshotArea').style.display = 'block'; document.getElementById('loginScreenshotImg').src = 'data:image/png;base64,' + b64; }
function hideAddForm() { unifiedClose(); }
function addAccountFormSubmit() { var form = document.querySelector('#addFormBox form'); if (form) form.submit(); }
function toggleKeepAlive(aid, checkbox) { fetch('/api/accounts/'+aid+'/keep_alive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keep_alive:checkbox.checked})}).then(safeJson).then(function(d){if(!d.success)checkbox.checked=!checkbox.checked}).catch(function(){checkbox.checked=!checkbox.checked}); }
function validateAccountForm() {
    var p = document.getElementById('addPlatInput').value; if (!p) { alert('请先选择平台'); return false; }
    // 通用「添加账号」框架：任何浏览器登录方式（密码/扫码/手机验证码）都必须走完
    // 「填写账号→验证码→获取Cookie→校验Cookie」完整流程才允许保存
    if (typeof _loginReadyToSave !== 'undefined' && !_loginReadyToSave) {
        var isEdit = document.getElementById('editAccountId').value ? true : false;
        var isBrowserMethod = (_loginMethod === 'password' || _loginMethod === 'qrcode' || _loginMethod === 'phone');
        if (!isEdit && isBrowserMethod) {
            alert('请先完成登录流程：点击「开始浏览器登录」→ 按提示处理验证码/扫码 → 等待Cookie校验通过 → 再点击「确认添加」保存');
            return false;
        }
    }
    var req = {'cfg_site_url':'平台地址','cfg_username':'用户名','cfg_password':'密码','cfg_app_password':'应用密码','cfg_app_id':'AppID','cfg_app_secret':'AppSecret','cfg_api_key':'API Key','cfg_api_secret':'API Secret','cfg_access_token':'Access Token','cfg_access_token_secret':'Access Token Secret'};
    var missing = []; for (var k in req) { var el = document.querySelector('input[name="'+k+'"]'); if (el && el.hasAttribute('required') && !el.value.trim()) missing.push(req[k]); }
    document.getElementById('accountForm').querySelectorAll('[required]').forEach(function(el) { if (!el.value.trim()) { var lb = el.closest('.form-group'); var lt = lb ? (lb.querySelector('label') ? lb.querySelector('label').textContent.trim() : el.name) : el.name; if (missing.indexOf(lt) === -1) missing.push(lt); } });
    if (missing.length > 0) { alert('请填写以下必填字段：\n• '+missing.join('\n• ')); return false; } return true;
}
function refreshAllStatuses(forceRefresh) {
    document.querySelectorAll('[id^="statusBadge_"]').forEach(function(span) {
        var id = span.id.replace('statusBadge_',''); var url = '/api/accounts/'+id+'/status'; if (forceRefresh) url += '?refresh=1';
        fetch(url).then(safeJson).then(function(data){if(data.success||data.logged_in!==undefined)renderDeepStatus(id,data)}).catch(function(){span.innerHTML='<span class="badge badge-secondary">⏳ 未知</span>'});
    });
}
function renderDeepStatus(aid, data) {
    var st=document.getElementById('onlineStatus_'+aid),bg=document.getElementById('statusBadge_'+aid),us=document.getElementById('userInfo_'+aid),lc=document.getElementById('lastCheck_'+aid); if(!st)return;
    if(bg){if(data.logged_in){var t=data.username?'✅ '+escapeHtml(data.username)+(data.points?' '+(data.points_label||'积分')+':'+data.points:''):'✅ 已登录';bg.innerHTML=t;bg.className='status-badge online';}else if(data.logged_in===false){bg.innerHTML='❌ '+escapeHtml(data.status||'未登录');bg.className='status-badge offline';}else if(data.logged_in===null&&data._cache_source){bg.innerHTML=escapeHtml(data.status||'⏳ 待确认');bg.className='status-badge pending';}else{bg.innerHTML='⏳ 未知';bg.className='status-badge unknown';}}
    var card=bg?bg.closest('.acct-card'):null;if(card){if(data.logged_in)card.dataset.status='online';else if(data.logged_in===false)card.dataset.status='offline';else card.dataset.status='pending';}
    if(us){if(data.logged_in&&data.username)us.innerHTML='<span style="color:#22c55e;font-weight:500;">'+escapeHtml(data.username)+'</span>'+(data.points?'<span style="color:#888;"> '+(data.points_label||'积分')+':'+data.points+'</span>':'')+(data.level?'<span style="color:#888;font-size:10px;"> '+escapeHtml(data.level)+'</span>':'');else if(data.logged_in)us.innerHTML='<span style="color:#22c55e;">✅ 已登录</span>';else if(data.logged_in===false)us.innerHTML='<span style="color:#ef4444;">❌ 未登录</span>';else if(data.logged_in===null)us.innerHTML='<span style="color:#f59e0b;">⏳ API检测通过，待Playwright确认</span>';else us.innerHTML='<span style="color:#999;">—</span>';}
    if(lc){var ca=data._cache_age_seconds;if(ca!==undefined)lc.innerHTML=ca<60?'<span style="color:#22c55e;">⏳ '+ca+'秒前</span>':ca<300?'<span style="color:#f59e0b;">⏳ '+Math.floor(ca/60)+'分前</span>':'<span style="color:#ef4444;">⏳ '+Math.floor(ca/60)+'分前</span>';else if(data.verified_at)lc.innerHTML='<span style="color:#888;">🕐 '+(data.verified_at.slice(0,16)||data.verified_at)+'</span>';}
    if(st){var ca=data._cache_age_seconds;st.innerHTML=ca!==undefined?(ca<60?'<span style="color:#22c55e;">⏳ '+ca+'秒前</span>':ca<300?'<span style="color:#f59e0b;">⏳ '+Math.floor(ca/60)+'分前</span>':'<span style="color:#ef4444;">⏳ '+Math.floor(ca/60)+'分前</span>'):'<span class="badge badge-secondary">⏳ 检测中...</span>';}
}
function checkStatus(aid) {
    document.getElementById('statusContent').innerHTML='<p style="color:#999;">⏳ 正在检测账号状态...</p>';document.getElementById('statusModal').style.display='flex';
    fetch('/api/accounts/'+aid+'/status?refresh=1').then(safeJson).then(function(data){
        if(!data.success&&data.logged_in===undefined){document.getElementById('statusContent').innerHTML='<div class="alert alert-error">❌ '+(data.error||'检测失败')+'</div>';return;}
        var h='<div style="margin-bottom:12px;"><p><strong>平台：</strong>'+(data.platform||'—')+'</p><p><strong>账号：</strong>'+escapeHtml(data.account_name||'')+'</p>';
        if(data.logged_in&&data.username){h+='<p><strong>用户名：</strong><span style="color:#22c55e;font-weight:600;font-size:16px;">'+escapeHtml(data.username)+'</span></p>';if(data.points)h+='<p><strong>'+(data.points_label||'积分')+'：</strong><span style="font-size:15px;color:#4361ee;">'+data.points+'</span></p>';if(data.level)h+='<p><strong>等级：</strong>'+escapeHtml(data.level)+'</p>';}
        if(data.display_name&&data.display_name!==data.username)h+='<p><strong>显示名：</strong>'+escapeHtml(data.display_name)+'</p>';
        h+='<p><strong>状态：</strong><span style="font-size:16px;">'+(data.status||'⏳ 未知')+'</span></p><p><strong>检测方法：</strong>'+(data.method||'Playwright')+'</p><p><strong>启用：</strong>'+(data.is_active?'✅ 是':'⛔ 否')+'</p><p><strong>Cookie：</strong>'+(data.has_cookie?'🍪 有':'— 无')+'</p>';
        if(data.verified_at)h+='<p><strong>检测时间：</strong>'+escapeHtml(data.verified_at)+'</p>';if(data._cache_source)h+='<p><strong>缓存来源：</strong>'+data._cache_source+'</p>';if(data.page_title)h+='<p><strong>页面标题：</strong>'+escapeHtml(data.page_title)+'</p>';h+='</div>';
        if(data.page_preview)h+='<div style="background:#f5f5f5;border:1px solid #e0e0e0;border-radius:6px;padding:12px;max-height:300px;overflow-y:auto;font-size:13px;line-height:1.6;"><div style="font-weight:600;margin-bottom:6px;color:#666;">📄 页面内容预览（前600字）</div><pre style="margin:0;white-space:pre-wrap;word-break:break-word;">'+escapeHtml(data.page_preview)+'</pre></div>';
        if(data.logged_in===false&&data.has_cookie)h+='<div class="alert alert-warning" style="margin-top:12px;">⚠️ Cookie 已失效，请重新使用"浏览器登录"获取新 Cookie</div>';
        document.getElementById('statusContent').innerHTML=h;renderDeepStatus(aid,data);
    }).catch(function(e){document.getElementById('statusContent').innerHTML='<div class="alert alert-error">❌ 请求失败: '+escapeHtml(e.message)+'</div>';});
}
function closeStatusModal(){document.getElementById('statusModal').style.display='none';}
function testSavedAccount(aid) {
    document.getElementById('statusContent').innerHTML='<p style="color:#999;">⏳ 正在验证账号凭证...（Playwright真实浏览器验证）</p>';document.getElementById('statusModal').style.display='flex';
    fetch('/api/accounts/test/'+aid,{method:'POST'}).then(safeJson).then(function(data){
        var h='<div style="margin-bottom:12px;"><p><strong>平台：</strong>'+(data.platform||'—')+'</p><p><strong>账号：</strong>'+escapeHtml(data.account_name||'')+'</p>';
        if(data.logged_in&&data.username){h+='<p><strong>用户名：</strong><span style="color:#22c55e;font-weight:600;font-size:16px;">'+escapeHtml(data.username)+'</span></p>';if(data.points)h+='<p><strong>'+(data.points_label||'积分')+'：</strong><span style="font-size:15px;color:#4361ee;">'+data.points+'</span></p>';if(data.level)h+='<p><strong>等级：</strong>'+escapeHtml(data.level)+'</p>';}
        h+='<p><strong>状态：</strong><span style="font-size:16px;">'+(data.status||'⏳ 未知')+'</span></p><p><strong>检测方法：</strong>'+(data.method||'Playwright')+'</p><p><strong>Cookie：</strong>'+(data.has_cookie?'🍪 有':'— 无')+'</p></div>';
        if(data.logged_in===false&&data.has_cookie)h+='<div class="alert alert-warning" style="margin-top:12px;">⚠️ Cookie 已失效，请使用「浏览器登录」重新获取 Cookie</div>';
        document.getElementById('statusContent').innerHTML=h;renderDeepStatus(aid,data);
    }).catch(function(e){document.getElementById('statusContent').innerHTML='<div class="alert alert-error">❌ 请求失败: '+escapeHtml(e.message)+'</div>';});
}
function testConnectionAdd() {
    var p=_loginPlatform;if(!p){alert('请先选择平台');return;}
    var f={};document.getElementById('accountForm').querySelectorAll('input[name^="cfg_"],textarea[name^="cfg_"]').forEach(function(i){f[i.name.replace('cfg_','')]=i.value.trim();});
    document.getElementById('statusContent').innerHTML='<p style="color:#999;">⏳ 正在测试连接...</p>';document.getElementById('statusModal').style.display='flex';
    fetch('/api/accounts/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:p,config:f})}).then(safeJson).then(function(d){
        var rd=d.result||d,pn=d.platform||rd.platform||p,il=rd.logged_in===true||(rd.status&&(rd.status.indexOf('已登录')>=0||rd.status.indexOf('✅')>=0)),dn=rd.username||rd.display_name||'',st=rd.status||d.status||'⏳ 未知',et=rd.error||d.error||'';
        var h='<div style="margin-bottom:12px;"><p><strong>平台：</strong>'+escapeHtml(pn)+'</p>';
        h+=il?'<div style="padding:12px;background:#f0fdf4;border:1px solid #22c55e;border-radius:8px;margin:8px 0;"><p style="font-size:20px;color:#22c55e;font-weight:600;">✅ 连接成功！</p>'+(dn?'<p><strong>用户名：</strong><span style="color:#22c55e;font-weight:600;">'+escapeHtml(dn)+'</span></p>':'')+'</div>':'<div style="padding:12px;background:#fef2f2;border:1px solid #ef4444;border-radius:8px;margin:8px 0;"><p style="font-size:20px;color:#ef4444;font-weight:600;">❌ '+(rd.logged_in===false?'连接失败':'无法验证')+'</p></div>';
        h+='<p><strong>状态：</strong>'+escapeHtml(st)+'</p>';if(et&&et!==st)h+='<p style="color:#ef4444;"><strong>错误：</strong>'+escapeHtml(et)+'</p>';h+='</div>';
        document.getElementById('statusContent').innerHTML=h;
    }).catch(function(e){document.getElementById('statusContent').innerHTML='<div class="alert alert-error">❌ 请求失败: '+escapeHtml(e.message)+'</div>';});
}
function toggleDebugCookie(){var a=document.getElementById('debugCookieArea'),t=document.getElementById('debugCookieToggle');if(a.style.display==='none'||a.style.display===''){a.style.display='block';t.textContent='🔧 关闭调试';t.style.color='#996600';}else{a.style.display='none';t.textContent='🔧 调试';t.style.color='#ccc';}}

// ====== 旧式渲染 + 简单功能 ======
function selectLoginMethod(method, methods) {
    _loginMethod=method;document.querySelectorAll('.login-method-tab').forEach(function(t){t.dataset.method===method?(t.style.background='#4361ee',t.style.color='#fff',t.style.borderColor='#4361ee'):(t.style.background='#f5f5f5',t.style.color='#333',t.style.borderColor='#ddd')});
    if(!methods){try{var plat=_loginPlatform;methods=[];for(var i=0;i<_platformSearchData.length;i++){if(_platformSearchData[i].name===plat){methods=_platformSearchData[i].login_methods||[];break}}}catch(e){methods=[]}}
    var md=methods.find(function(m){return m.method===method});renderMethodFields(method,md?(md.fields||[]):[],md);
}
function renderMethodFields(method,fields,methodDef) {
    var platform=_loginPlatform,descDiv=document.getElementById('loginMethodContent'),preset=_presetsData[platform],html='';
    showLoginMethodDemo(method);
    if(methodDef&&methodDef.description)html+='<div style="font-size:12px;color:#888;margin-bottom:10px;line-height:1.5;">💡 '+escapeHtml(methodDef.description)+'</div>';
    var hasSiteUrl=fields.indexOf('site_url')>=0;
    if(preset&&preset.sites&&preset.sites.length>0){html+='<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">📌 知名站点（点击自动填充）</label><div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px;">';preset.sites.forEach(function(s){html+='<button type="button" class="btn btn-sm btn-outline" style="font-size:11px;border:1px solid #ddd;border-radius:4px;padding:3px 8px;background:#f5f5f5;cursor:pointer;" onclick="fillPreset(\''+escapeHtml(s.name)+'\',\''+escapeHtml(s.url||'')+'\',\''+escapeHtml(s.desc||'')+'\')" title="'+escapeHtml(s.desc||'')+'">'+escapeHtml(s.name||'')+'</button>'});html+='</div>';}
    fields.forEach(function(fk){
        if(fk==='site_url'){var val='';if(_loginCapData&&_loginCapData.site_url_default)val=_loginCapData.site_url_default;else if(preset&&preset.sites&&preset.sites.length>0)val=preset.sites[0].url||'';html+='<div class="form-group"><label>平台地址</label><input type="text" name="cfg_site_url" placeholder="https://..."'+(val?' value="'+val+'"':'')+' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';}
        else if(fk==='username')html+='<div class="form-group"><label>用户名/邮箱</label><input type="text" name="cfg_username" placeholder="登录用户名或邮箱" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        else if(fk==='password')html+='<div class="form-group"><label>密码</label><input type="password" name="cfg_password" placeholder="登录密码" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        else if(fk==='phone')html+='<div class="form-group"><label>手机号码</label><input type="text" name="cfg_phone" placeholder="手机号码" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        else if(fk==='app_password')html+='<div class="form-group"><label>应用密码</label><input type="password" name="cfg_app_password" placeholder="应用密码" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        else if(fk==='app_id')html+='<div class="form-group"><label>AppID</label><input type="text" name="cfg_app_id" placeholder="微信公众号 AppID" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        else if(fk==='app_secret')html+='<div class="form-group"><label>AppSecret</label><input type="password" name="cfg_app_secret" placeholder="微信公众号 AppSecret" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
        else if(fk==='cookie')html+='<div class="form-group"><label>Cookie <span style="color:#999;font-size:12px;">（从浏览器 F12 复制）</span></label><textarea name="cfg_cookie" rows="3" placeholder="粘贴完整的 Cookie 字符串" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-family:monospace;font-size:11px;"></textarea></div>';
        else html+='<div class="form-group"><label>'+escapeHtml(fk)+'</label><input type="text" name="cfg_'+fk+'" style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';
    });
    descDiv.innerHTML=html;
    // 切换登录方式时清除验证码区域（防止残留）
    hideCaptchaInput();
    document.getElementById('loginScreenshotArea').style.display='none';
    document.getElementById('loginStatusMsg').style.display='none';
    _isLoginRunning=false;
    var btnStart=document.getElementById('btnStartLogin'),btnCaptcha=document.getElementById('btnCaptchaLogin'),btnRefresh=document.getElementById('btnRefreshScreenshot'),sa=document.getElementById('loginScreenshotArea');
    if(method==='password'){btnStart.style.display='inline-block';btnStart.textContent='🚀 开始浏览器登录';btnStart.disabled=false;btnCaptcha.style.display='none';btnRefresh.style.display='none';sa.style.display='none';}
    else if(method==='qrcode'){btnStart.style.display='inline-block';btnStart.textContent='📱 打开扫码登录页';btnStart.disabled=false;btnCaptcha.style.display='none';btnRefresh.style.display='none';sa.style.display='none';}
    else if(method==='phone'){btnStart.style.display='inline-block';btnStart.textContent='📱 发送验证码';btnStart.disabled=false;btnCaptcha.style.display='none';btnRefresh.style.display='none';sa.style.display='none';}
    else{btnStart.style.display='none';btnCaptcha.style.display='none';btnRefresh.style.display='none';sa.style.display='none';}
    document.getElementById('loginStatusMsg').style.display='none';_isLoginRunning=false;
    var tc=document.getElementById('btnTestConnectionAdd');if(method==='cookie'||method==='oauth1'||method==='bearer'||method==='password')tc.style.display='inline-block';else tc.style.display='none';
}
function fillPreset(name,url,desc){var si=document.querySelector('input[name="cfg_site_url"]');if(si&&url)si.value=url;var ni=document.getElementById('addAccountName');if(ni&&!ni.value)ni.value=name;}
function renderConfigFields(fields) {
    document.getElementById('loginMethodTabs').innerHTML='';var platform=_loginPlatform,preset=_presetsData[platform],html='';
    if(preset&&preset.sites&&preset.sites.length>0){html+='<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">📌 知名站点</label><div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px;">';preset.sites.forEach(function(s){html+='<button type="button" class="btn btn-sm btn-outline" style="font-size:11px;border:1px solid #ddd;border-radius:4px;padding:3px 8px;background:#f5f5f5;cursor:pointer;" onclick="fillPreset(\''+escapeHtml(s.name)+'\',\''+escapeHtml(s.url||'')+'\',\''+escapeHtml(s.desc||'')+'\')">'+escapeHtml(s.name||'')+'</button>'});html+='</div>';}
    fields.forEach(function(f){var t=f.type==='password'?'password':'text',val='';if(f.key==='site_url'&&preset&&preset.sites&&preset.sites.length>0)val=preset.sites[0].url||'';html+='<div class="form-group"><label>'+(f.label||f.key)+'</label><input type="'+t+'" name="cfg_'+f.key+'" placeholder="'+(f.placeholder||'')+'"'+(val?' value="'+val+'"':'')+' style="width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;"></div>';});
    document.getElementById('loginMethodContent').innerHTML=html;document.getElementById('loginStatusMsg').style.display='none';document.getElementById('btnStartLogin').style.display='none';document.getElementById('btnCaptchaLogin').style.display='none';document.getElementById('btnRefreshScreenshot').style.display='none';document.getElementById('btnTestConnectionAdd').style.display='none';var sa=document.getElementById('loginScreenshotArea');if(sa)sa.style.display='none';
}
function renderCaptchaSection(captchaInfo){if(!captchaInfo||!captchaInfo.has_captcha)return'';var n=captchaInfo.note||'',types=captchaInfo.types||[],tH='';if(types.length>0)tH='<div style="font-size:11px;color:#888;margin-bottom:6px;">验证码类型: '+escapeHtml(types.join(', '))+'</div>';var nH='';if(n)nH='<div style="font-size:11px;color:#996600;margin-bottom:8px;padding:4px 8px;background:#fff8e1;border-radius:4px;">💡 '+escapeHtml(n)+'</div>';return '<div style="margin-top:10px;padding:12px;background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;"><div style="font-weight:600;font-size:13px;margin-bottom:6px;">🔐 验证码验证</div>'+tH+nH+'<div style="display:flex;gap:6px;flex-wrap:wrap;"><button type="button" class="btn btn-sm btn-primary" onclick="loadCaptchaScreenshot()">📸 加载验证码截图</button></div></div>';}
function loadCaptchaScreenshot(){var p=_loginPlatform,img=document.getElementById('loginScreenshotImg'),area=document.getElementById('loginScreenshotArea');if(img)img.src='';if(area)area.style.display='none';fetch('/api/captcha/'+p+'/screenshot').then(safeJson).then(function(d){if(d.success&&d.image){if(area)area.style.display='block';if(img)img.src='data:image/png;base64,'+d.image}}).catch(function(){});}
function showLoginMethodDemo(method){
    var dd=document.getElementById('loginMethodDemo');if(!dd)return;
    var im={'password':'/static/images/demo/password-login.svg','qrcode':'/static/images/demo/qrcode-login.svg','cookie':'/static/images/demo/cookie-paste.svg','phone':'/static/images/demo/password-login.svg','oauth1':'/static/images/demo/password-login.svg'};
    var di=document.getElementById('loginDemoImage');if(di&&im[method]){di.src=im[method];document.getElementById('loginDemoImageArea').style.display='block';}else if(di){document.getElementById('loginDemoImageArea').style.display='none';}
    fetch('/api/login/method-demo/'+encodeURIComponent(method)).then(safeJson).then(function(d){if(!d.success||!d.demo){dd.style.display='none';return;}var demo=d.demo;document.getElementById('loginDemoTitle').textContent=demo.title||'';var sh='';if(demo.steps){demo.steps.forEach(function(s){sh+='<div style="display:flex;align-items:flex-start;gap:6px;margin-bottom:2px;"><span style="color:#4361ee;flex-shrink:0;">▸</span><span>'+escapeHtml(s)+'</span></div>'});}document.getElementById('loginDemoSteps').innerHTML=sh;if(demo.note){document.getElementById('loginDemoNote').textContent='💡 '+demo.note;document.getElementById('loginDemoNote').style.display='block';}else{document.getElementById('loginDemoNote').style.display='none';}dd.style.display='block';}).catch(function(){dd.style.display='none';});
}

// ====== 登录进度条控制 ======
function resetProgressBar(){var bar=document.getElementById('loginProgressBar');bar.style.display='block';document.querySelectorAll('.prog-step').forEach(function(s){s.style.background='#e0e0e0';s.style.color='#999';s.querySelector('.prog-icon').textContent='⏳'});document.getElementById('progDetail').textContent='';}
function setStepActive(step,detail){var el=document.querySelector('.prog-step[data-step="'+step+'"]');if(!el)return;el.style.background='#d1ecf1';el.style.color='#0c5460';el.querySelector('.prog-icon').textContent='⏳';if(detail)document.getElementById('progDetail').textContent=detail;}
function setStepDone(step,detail){var el=document.querySelector('.prog-step[data-step="'+step+'"]');if(!el)return;el.style.background='#d4edda';el.style.color='#155724';el.querySelector('.prog-icon').textContent='✅';if(detail)document.getElementById('progDetail').textContent=detail;}
function setStepFailed(step,detail){var el=document.querySelector('.prog-step[data-step="'+step+'"]');if(!el)return;el.style.background='#f8d7da';el.style.color='#721c24';el.querySelector('.prog-icon').textContent='❌';if(detail)document.getElementById('progDetail').textContent='❌ '+detail;document.getElementById('progDetail').style.color='#721c24';}
function showCaptchaInput(imageBase64,needAmobbsHack,captchaImageUrl){var src=imageBase64?'data:image/png;base64,'+imageBase64:(captchaImageUrl||'');document.getElementById('loginScreenshotArea').style.display='block';document.getElementById('loginScreenshotImg').src=src;document.getElementById('captchaInputArea').style.display='block';document.getElementById('captchaImage').src=src;document.getElementById('captchaCodeInput').value='';document.getElementById('captchaCodeInput').focus();document.getElementById('captchaFeedback').style.display='none';document.getElementById('btnCaptchaLogin').style.display='none';document.getElementById('btnRefreshScreenshot').style.display='inline-block';var noteEl=document.getElementById('discuzCaptchaNote');if(noteEl)noteEl.remove();var isDiscuz=(_loginCapData&&_loginCapData.engine==='discuz')||_loginPlatform==='amobbs'||_loginPlatform==='mydigit'||_loginPlatform==='discuz'||needAmobbsHack;if(isDiscuz){var note=document.createElement('div');note.id='discuzCaptchaNote';note.style.cssText='margin-top:6px;padding:6px 10px;background:#e3f2fd;border:1px solid #90caf9;border-radius:6px;font-size:11px;color:#1565c0;';var pname=document.getElementById('addPlatName');var dname=pname?pname.textContent:'Discuz 论坛';note.innerHTML='💡 '+dname+' 提示：输入验证码后点击边框附近区域触发 ✓ 核验，通过后自动登录';document.getElementById('captchaInputArea').appendChild(note);}setStepActive(4,'等待输入验证码'+(isDiscuz?'（'+dname+' 需点击边框核验）':''));}
function hideCaptchaInput(){document.getElementById('captchaInputArea').style.display='none';document.getElementById('captchaImage').src='';document.getElementById('captchaCodeInput').value='';var note=document.getElementById('discuzCaptchaNote');if(note)note.remove();}
function showCaptchaFeedback(text,isError){var fb=document.getElementById('captchaFeedback');fb.style.display='block';fb.style.color=isError?'#ef4444':'#22c55e';fb.textContent=isError?'❌ '+text:'✅ '+text;}
function unifiedSaveOnly(){if(_qrSessionId){fetch('/api/login/qrcode/'+_loginPlatform+'/close/'+_qrSessionId,{method:'POST'}).catch(function(){});if(_qrPollTimer)clearInterval(_qrPollTimer);_qrPollTimer=null;_qrSessionId=null;}if(_isLoginRunning||_loginSession){fetch('/api/platform/'+_loginPlatform+'/login/close',{method:'POST'}).catch(function(){});}_isLoginRunning=false;_loginSession=null;_loginReadyToSave=false;_loginResultCookie='';var form=document.querySelector('#addFormBox form');if(form)form.submit();}
function unifiedClose(){if(_qrSessionId){fetch('/api/login/qrcode/'+_loginPlatform+'/close/'+_qrSessionId,{method:'POST'}).catch(function(){});if(_qrPollTimer)clearInterval(_qrPollTimer);_qrPollTimer=null;_qrSessionId=null;}if(_isLoginRunning||_loginSession||_loginReadyToSave){fetch('/api/platform/'+_loginPlatform+'/login/close',{method:'POST'}).catch(function(){});}_isLoginRunning=false;_loginSession=null;_loginReadyToSave=false;_loginResultCookie='';var saveBtn=document.getElementById('btnSaveOnly');if(saveBtn){saveBtn.textContent='保存';saveBtn.className='btn btn-success';saveBtn.style.fontWeight='';saveBtn.style.fontSize='';}document.getElementById('addFormBox').style.display='none';}
