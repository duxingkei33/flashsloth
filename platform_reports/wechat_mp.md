# Platform Exploration Report: WeChat Official Account

> **Exploration Date**: 2026-07-07 11:54:34
> **Method**: Playwright page analysis + API documentation
> **Account Status**: NOT CONFIGURED (needs AppID + AppSecret)
> **Site**: https://mp.weixin.qq.com

---

## 1. Login Status

| Item | Value |
|------|-------|
| Login URL | `https://mp.weixin.qq.com/` |
| Page Title | 微信公众平台 |
| Password Login | Not detected |
| QR Code | Available |
| Visible Inputs | 0 |
| Recommended (API) | AppID + AppSecret |
| Recommended (Browser) | WeChat QR Scan |

### Input Fields

## 2. Publishing Capabilities

WeChat uses official REST API (not Playwright):

| Operation | API Endpoint | Method |
|-----------|-------------|--------|
| Create Draft | `/cgi-bin/draft/add` | POST |
| Update Draft | `/cgi-bin/draft/update` | POST |
| Get Draft | `/cgi-bin/draft/get` | POST |
| Delete Draft | `/cgi-bin/draft/delete` | POST |
| List Drafts | `/cgi-bin/draft/batchget` | POST |
| Submit Publish | `/cgi-bin/freepublish/submit` | POST |
| List Published | `/cgi-bin/freepublish/batchget` | POST |

### Content Format Restrictions

Supported: `<p>`, `<strong>`, `<em>`, `<img>`, `<a>`, `<blockquote>`, `<code>`, `<h1-h4>`, `<ul>/<ol>`, `<hr>`
NOT supported: Tables, iframe, external images, JavaScript, CSS class/style

## 3. Image Upload

| API | `/cgi-bin/material/add_material?type=image` |
| Method | `multipart/form-data POST` |
| Auth | access_token |
| Formats | bmp, png, jpeg, jpg, gif |
| Max Size | 10MB |
| Limit | 100,000 permanent materials total |

## 4. Sign-In

Not supported.

## 5. Collection Capabilities

| Operation | API | Requires |
|-----------|-----|----------|
| Draft List | `/cgi-bin/draft/batchget` | access_token |
| Published List | `/cgi-bin/freepublish/batchget` | access_token |
| Material List | `/cgi-bin/material/batchget_material` | access_token |

## 6. Current State

| Component | Status |
|-----------|--------|
| Exploration Report | DONE |
| Publisher | EXISTS (`plugins/publisher_wechat.py`) |
| SDK Adapter | EXISTS (`sdk/adapters/wechat.py`) |
| Login Plugin | NOT CREATED |
| Account Config | NOT CONFIGURED |
| Image Upload | PARTIAL (stub only) |
| Cover Image | NOT IMPLEMENTED |

## 7. Gap List

1. **Image upload pipeline** - Upload images to WeChat material before inserting into HTML
2. **Cover image** - Implement article.cover -> upload as thumbnail
3. **Summary generation** - Auto-generate digest from body (120 char limit)
4. **Test connection** - AppID+AppSecret -> token validation
5. **Login plugin** - Playwright QR code login (reference bilibili_login.py)

## 8. Special Notes

1. AppID + AppSecret from mp.weixin.qq.com -> Development -> Basic Config
2. access_token expires in 2 hours, auto-refresh in publisher
3. 100k permanent material limit, periodic cleanup recommended
4. API can only save drafts - publish needs phone confirmation
5. External image URLs NOT allowed in article HTML
6. Daily publish limit: Subscription 1/day, Service 4/month
7. Draft/Publish APIs are the latest WeChat interfaces (2022+)
