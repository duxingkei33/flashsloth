// ====== 搜索/过滤/排序/批量/视图切换 ======

// ─── 搜索与过滤 (优化1 — 增强版: debounce + 站点URL搜索) ───
function filterAccounts() {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(function() {
        _doFilterAccounts();
    }, 200);
}

// 回车键立即搜索
function filterAccountsImmediate(e) {
    if (e.key === 'Enter') {
        clearTimeout(_searchTimer);
        _doFilterAccounts();
    }
}

function _doFilterAccounts() {
    const q = document.getElementById('searchInput').value.toLowerCase().trim();
    const p = document.getElementById('filterPlatform').value;
    const s = document.getElementById('filterStatus').value;
    const cards = document.querySelectorAll('.acct-card');
    let visible = 0;

    cards.forEach(function(card) {
        const name = (card.dataset.name || '').toLowerCase();
        const platform = card.dataset.platform || '';
        const status = card.dataset.status || 'unknown';
        const siteUrl = (card.dataset.siteUrl || '').toLowerCase();
        const isEnabled = !card.classList.contains('disabled');

        // Search: name + platform + site_url
        let match = true;
        if (q) {
            match = name.includes(q) || platform.includes(q) || siteUrl.includes(q);
        }
        if (match && p) {
            match = platform === p;
        }
        if (match && s) {
            if (s === 'enabled') match = isEnabled;
            else if (s === 'disabled') match = !isEnabled;
            else if (s === 'pending') match = status === 'pending' || status === 'unknown';
            else match = status === s;
        }

        card.style.display = match ? '' : 'none';
        if (match) visible++;
    });

    // 隐藏/显示空的分组
    document.querySelectorAll('.card[data-platform]').forEach(function(group) {
        const visibleCards = group.querySelectorAll('.acct-card:not([style*="display: none"])');
        if (visibleCards.length === 0) {
            group.style.display = 'none';
        } else {
            group.style.display = '';
        }
    });

    document.getElementById('filterCount').textContent = '显示 ' + visible + ' / ' + cards.length + ' 个账号';
}

// ─── 排序 (优化6) ───
function sortAccounts(field) {
    // 切换排序方向
    if (_currentSort === field) {
        _sortAsc = !_sortAsc;
    } else {
        _currentSort = field;
        _sortAsc = true;
    }

    // 更新按钮样式
    document.querySelectorAll('.sort-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.sort === field);
    });

    // 获取所有分组卡片
    const container = document.getElementById('accountsContainer');
    const groups = Array.from(container.querySelectorAll('.card[data-platform]'));

    groups.sort(function(a, b) {
        const nameA = a.querySelector('.plat-header h2').textContent.trim();
        const nameB = b.querySelector('.plat-header h2').textContent.trim();
        // 内部卡片排序
        var cardsA = Array.from(a.querySelectorAll('.acct-card'));
        var cardsB = Array.from(b.querySelectorAll('.acct-card'));

        if (field === 'name') {
            cardsA.sort(function(x, y) { return _sortAsc ? x.dataset.name.localeCompare(y.dataset.name) : y.dataset.name.localeCompare(x.dataset.name); });
            cardsB.sort(function(x, y) { return _sortAsc ? x.dataset.name.localeCompare(y.dataset.name) : y.dataset.name.localeCompare(x.dataset.name); });
        } else if (field === 'status') {
            var order = {online: 0, pending: 1, unknown: 2, offline: 3};
            cardsA.sort(function(x, y) {
                var xo = order[x.dataset.status] || 99;
                var yo = order[y.dataset.status] || 99;
                return _sortAsc ? xo - yo : yo - xo;
            });
            cardsB.sort(function(x, y) {
                var xo = order[x.dataset.status] || 99;
                var yo = order[y.dataset.status] || 99;
                return _sortAsc ? xo - yo : yo - xo;
            });
        } else if (field === 'lastcheck') {
            cardsA.sort(function(x, y) {
                var xc = parseFloat(x.dataset.lastCheck) || 0;
                var yc = parseFloat(y.dataset.lastCheck) || 0;
                return _sortAsc ? xc - yc : yc - xc;
            });
            cardsB.sort(function(x, y) {
                var xc = parseFloat(x.dataset.lastCheck) || 0;
                var yc = parseFloat(y.dataset.lastCheck) || 0;
                return _sortAsc ? xc - yc : yc - xc;
            });
        } else {
            // 按平台分组排序
            return _sortAsc ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
        }

        // 重新附加排序后的卡片
        cardsA.forEach(function(c) { a.appendChild(c); });
        cardsB.forEach(function(c) { b.appendChild(c); });
        return 0;
    });

    groups.forEach(function(g) { container.appendChild(g); });
}

// ─── 视图切换 (优化5) ───
function setViewMode(mode) {
    document.querySelectorAll('.view-toggle button').forEach(function(btn) {
        btn.classList.toggle('active', btn.textContent.includes(mode === 'card' ? '卡片' : '列表'));
    });
    document.getElementById('accountsContainer').className = mode === 'card' ? 'card-view' : 'compact-view';
}

// ─── 最后检测时间自动更新 (优化2 — 客户端定时器) ───
function startTimeAutoUpdater() {
    // 每10秒更新一次所有 "X秒前" / "X分前" 时间标签
    setInterval(function() {
        document.querySelectorAll('#accountsContainer .time-tag').forEach(function(tag) {
            var text = tag.textContent.trim();
            // 匹配 "⏳ N秒前" 或 "⏳ N分前"
            var secMatch = text.match(/⏳\s*(\d+)\u79d2\u524d/);
            var minMatch = text.match(/⏳\s*(\d+)\u5206\u524d/);
            if (secMatch) {
                var secs = parseInt(secMatch[1]) + 10;
                if (secs >= 60) {
                    tag.innerHTML = '<span style="color:#f59e0b;">⏳ 1分前</span>';
                } else {
                    tag.innerHTML = '<span style="color:#22c55e;">⏳ ' + secs + '秒前</span>';
                }
            } else if (minMatch) {
                var mins = parseInt(minMatch[1]);
            }
        });
    }, 10000);
}

// ─── 批量操作 (优化3) ───
function toggleSelectAll(cb) {
    document.querySelectorAll('.acct-checkbox').forEach(function(c) { c.checked = cb.checked; });
    updateBatchBar();
}

function updateBatchBar() {
    var checked = document.querySelectorAll('.acct-checkbox:checked');
    var bar = document.getElementById('batchToolbar');
    var count = checked.length;
    document.getElementById('batchCount').textContent = '已选 ' + count + ' 个';

    if (count > 0) {
        bar.classList.add('show');
    } else {
        bar.classList.remove('show');
        document.getElementById('selectAllAccounts').checked = false;
    }
}

function clearSelection() {
    document.querySelectorAll('.acct-checkbox').forEach(function(c) { c.checked = false; });
    updateBatchBar();
}

function getSelectedIds() {
    var ids = [];
    document.querySelectorAll('.acct-checkbox:checked').forEach(function(c) {
        ids.push(parseInt(c.value));
    });
    return ids;
}

function batchToggle(enable) {
    var ids = getSelectedIds();
    if (ids.length === 0) { alert('请先选择账号'); return; }
    var action = enable ? '启用' : '禁用';
    if (!confirm('确定' + action + '选中的 ' + ids.length + ' 个账号？')) return;

    fetch('/api/accounts/batch/toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: ids, enable: enable})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            alert(data.message);
            location.reload();
        } else {
            alert('操作失败: ' + (data.error || '未知错误'));
        }
    })
    .catch(function(e) { alert('网络错误: ' + e.message); });
}

function batchDelete() {
    var ids = getSelectedIds();
    if (ids.length === 0) { alert('请先选择账号'); return; }
    if (!confirm('⚠️ 确定删除选中的 ' + ids.length + ' 个账号？此操作不可恢复！')) return;

    fetch('/api/accounts/batch/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: ids})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            alert(data.message);
            location.reload();
        } else {
            alert('删除失败: ' + (data.error || '未知错误'));
        }
    })
    .catch(function(e) { alert('网络错误: ' + e.message); });
}

// ─── 启用/禁用切换 ───
function toggleAccount(aid, checkbox) {
    fetch('/api/accounts/' + aid + '/toggle', {method: 'POST'})
    .then(r => r.json())
    .then(data => {
        if (data.success) { location.reload(); }
        else { checkbox.checked = !checkbox.checked; alert('操作失败: ' + (data.error || '未知错误')); }
    })
    .catch(e => { checkbox.checked = !checkbox.checked; alert('网络错误: ' + e.message); });
}

// ====== 平台模糊搜索/自动补全 ======
function onPlatformSearchInput() {
    clearTimeout(_platformSearchTimer);
    var input = document.getElementById('platformSearchInput');
    var q = input.value.trim();

    // 用户重新输入 → 清除已选状态
    input.dataset.selected = '';
    document.getElementById('btnAddAccount').disabled = true;

    // 空输入 → 展示全量平台列表（combobox 行为）
    if (!q) {
        _loadAllPlatformsForDropdown();
        _platformSearchIdx = -1;
        return;
    }

    _platformSearchTimer = setTimeout(function() {
        _doPlatformSearch(q);
    }, 300);
}

function onPlatformSearchFocus() {
    // 聚焦时展示全量平台列表（combobox 行为）
    _loadAllPlatformsForDropdown();
}

function _loadAllPlatformsForDropdown() {
    var dd = document.getElementById('platformSearchDropdown');
    dd.innerHTML = '<div class="plat-loading">⏳ 加载平台列表...</div>';
    dd.style.display = 'block';

    // 跟踪是否已经重试过
    var hasRetried = false;
    var timedOut = false;
    var timeoutTimer = null;

    function showTimeout() {
        timedOut = true;
        dd.innerHTML = '<div class="plat-empty">'
            + '⏰ 加载超时，<a href="javascript:_loadAllPlatformsForDropdown()" style="text-decoration:underline;cursor:pointer;color:var(--accent)">点击重试</a>'
            + '</div>';
    }

    // 5 秒超时检测
    timeoutTimer = setTimeout(showTimeout, 5000);

    function doFetch() {
        fetch('/api/platforms/search?q=')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            clearTimeout(timeoutTimer);
            if (data.success && data.results) {
                _platformSearchData = data.results;
                _renderPlatformDropdown(data.results);
            } else {
                dd.innerHTML = '<div class="plat-empty">加载失败</div>';
            }
        })
        .catch(function() {
            if (!hasRetried) {
                // 第 1 次失败 → 等待 1 秒后自动重试
                hasRetried = true;
                dd.innerHTML = '<div class="plat-loading">⏳ 重试中...</div>';
                setTimeout(doFetch, 1000);
            } else {
                clearTimeout(timeoutTimer);
                if (!timedOut) {
                    dd.innerHTML = '<div class="plat-empty">网络错误，<a href="javascript:_loadAllPlatformsForDropdown()" style="text-decoration:underline;cursor:pointer;color:var(--accent)">点击重试</a></div>';
                }
                // 如果已经显示超时消息，则保留超时消息
            }
        });
    }

    doFetch();
}

// ====== 切換下拉面板显示/隐藏（全量列表） ======
function togglePlatformDropdown() {
    var dd = document.getElementById('platformSearchDropdown');
    if (dd.style.display === 'block') {
        dd.style.display = 'none';
    } else {
        _loadAllPlatformsForDropdown();
    }
}

function _doPlatformSearch(q) {
    var dd = document.getElementById('platformSearchDropdown');
    dd.innerHTML = '<div class="plat-loading">🔍 搜索中...</div>';
    dd.style.display = 'block';

    fetch('/api/platforms/search?q=' + encodeURIComponent(q))
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success || !data.results) {
            dd.innerHTML = '<div class="plat-empty">搜索失败</div>';
            return;
        }
        _platformSearchData = data.results;
        if (data.results.length === 0) {
            dd.innerHTML = '<div class="plat-empty">未找到匹配「' + escapeHtml(q) + '」的平台</div>';
            return;
        }
        _renderPlatformDropdown(data.results);
    })
    .catch(function() {
        dd.innerHTML = '<div class="plat-empty">网络错误，请重试</div>';
    });
}

function _renderPlatformDropdown(results) {
    var dd = document.getElementById('platformSearchDropdown');
    _platformSearchIdx = -1;
    var html = '';
    for (var i = 0; i < results.length; i++) {
        var r = results[i];
        var icon = getPlatformIconCode(r.name);
        html += '<div class="plat-item" data-index="' + i + '" onclick="onPlatformSelect(\'' + escapeHtml(r.name) + '\')"'
             + ' onmouseenter="this.classList.add(\'active\');_platformSearchIdx=' + i + ';"'
             + ' onmouseleave="this.classList.remove(\'active\');">'
             + '<span class="plat-icon" style="background:' + getPlatformColor(r.name) + ';">' + icon + '</span>'
             + '<div class="plat-info">'
             + '<div class="plat-name">➕ ' + escapeHtml(r.display_name) + '</div>'
             + '<div class="plat-arch">' + escapeHtml(r.architecture) + '</div>'
             + '</div>'
             + '</div>';
    }
    dd.innerHTML = html;
    dd.style.display = 'block';

    // 如果没有滚动条，选中第一项
    if (results.length > 0) {
        var first = dd.querySelector('.plat-item');
        if (first) { first.classList.add('active'); _platformSearchIdx = 0; }
    }
}

function onPlatformSearchKeydown(e) {
    var dd = document.getElementById('platformSearchDropdown');
    if (dd.style.display !== 'block') return;

    var items = dd.querySelectorAll('.plat-item');
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        items.forEach(function(item) { item.classList.remove('active'); });
        _platformSearchIdx = Math.min(_platformSearchIdx + 1, items.length - 1);
        items[_platformSearchIdx].classList.add('active');
        items[_platformSearchIdx].scrollIntoView({block: 'nearest'});
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        items.forEach(function(item) { item.classList.remove('active'); });
        _platformSearchIdx = Math.max(_platformSearchIdx - 1, 0);
        items[_platformSearchIdx].classList.add('active');
        items[_platformSearchIdx].scrollIntoView({block: 'nearest'});
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (_platformSearchIdx >= 0 && _platformSearchIdx < items.length) {
            var activeItem = items[_platformSearchIdx];
            var name = activeItem.getAttribute('onclick');
            // Extract the platform name from the onclick attribute
            var match = name.match(/onPlatformSelect\('([^']+)'\)/);
            if (match) {
                onPlatformSelect(match[1]);
            }
        }
    } else if (e.key === 'Escape') {
        dd.style.display = 'none';
    }
}

function onPlatformSelect(name) {
    var input = document.getElementById('platformSearchInput');
    input.dataset.selected = name;
    // Find the display name from cached data
    var displayName = name;
    for (var i = 0; i < _platformSearchData.length; i++) {
        if (_platformSearchData[i].name === name) {
            displayName = _platformSearchData[i].display_name;
            break;
        }
    }
    input.placeholder = '✅ ' + displayName;
    input.value = '';
    document.getElementById('platformSearchDropdown').style.display = 'none';
    document.getElementById('btnAddAccount').disabled = false;
}

// 点击外部关闭下拉框
document.addEventListener('click', function(e) {
    var wrap = document.querySelector('.platform-search-wrap');
    var dd = document.getElementById('platformSearchDropdown');
    if (wrap && dd && !wrap.contains(e.target)) {
        dd.style.display = 'none';
    }
});


