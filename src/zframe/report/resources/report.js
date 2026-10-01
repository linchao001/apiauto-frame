/* ZFrame enhanced HTML report UI (injected by polish_report_html). */
(function () {
  "use strict";

  var RESULT_ORDER = [
    "failed",
    "error",
    "passed",
    "skipped",
    "xfailed",
    "xpassed",
    "rerun",
    "retried",
  ];

  var RESULT_LABEL = {
    failed: "失败 Failed",
    error: "错误 Error",
    passed: "通过 Passed",
    skipped: "跳过 Skipped",
    xfailed: "预期失败 xFailed",
    xpassed: "意外通过 xPassed",
    rerun: "重跑 Rerun",
    retried: "重试 Retried",
  };

  var STAT_META = [
    { key: "failed", label: "失败", icon: "✕" },
    { key: "error", label: "错误", icon: "!" },
    { key: "passed", label: "通过", icon: "✓" },
    { key: "skipped", label: "跳过", icon: "–" },
    { key: "total", label: "总计", icon: "Σ" },
  ];

  var KIND_ORDER = ["E2E", "API", "Other"];

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function classifyKind(testId) {
    var id = String(testId || "").replace(/\\/g, "/");
    if (/\/E2E\//i.test(id)) return "E2E";
    if (/\/API\//i.test(id)) return "API";
    return "Other";
  }

  function resultKey(result) {
    return String(result || "").toLowerCase();
  }

  function decodeBlob(raw) {
    if (!raw) return null;
    // getAttribute() already returns entity-decoded text. Do NOT pass the JSON
    // through innerHTML — caseTitle embeds HTML and would corrupt the payload.
    try {
      return JSON.parse(raw);
    } catch (err) {
      console.error("zframe report: bad data-jsonblob", err);
      return null;
    }
  }

  function flattenTests(blob) {
    var tests = (blob && blob.tests) || {};
    var out = [];
    Object.keys(tests).forEach(function (key) {
      var rows = tests[key] || [];
      rows.forEach(function (row, idx) {
        out.push(
          Object.assign({}, row, {
            _uid: key + "::" + idx,
            _kind: classifyKind(row.testId || key),
            _result: resultKey(row.result),
          })
        );
      });
    });
    return out;
  }

  function countByResult(tests) {
    var counts = { total: tests.length };
    RESULT_ORDER.forEach(function (k) {
      counts[k] = 0;
    });
    tests.forEach(function (t) {
      var k = t._result;
      if (counts[k] === undefined) counts[k] = 0;
      counts[k] += 1;
    });
    return counts;
  }

  function stripParamId(name) {
    // test_foo[E2E001] / test_foo[T001] → test_foo
    return String(name || "").replace(/\[[^\]]*\]$/g, "");
  }

  function parseNodeId(testId) {
    var id = String(testId || "");
    var parts = id.split("::").filter(function (p) {
      return p.length > 0;
    });
    // Drop file path (first segment).
    var rest = parts.slice(1);
    if (rest.length && /^(setup|call|teardown)$/i.test(rest[rest.length - 1])) {
      rest.pop();
    }
    if (rest.length >= 2) {
      return {
        className: rest[0],
        caseName: stripParamId(rest.slice(1).join("::")),
      };
    }
    if (rest.length === 1) {
      return { className: "", caseName: stripParamId(rest[0]) };
    }
    return { className: "", caseName: stripParamId(id) || "(unnamed)" };
  }

  function treeCaseLabel(test) {
    var parsed = parseNodeId(test.testId);
    if (parsed.className && parsed.caseName) {
      return parsed.className + " · " + parsed.caseName;
    }
    return parsed.caseName || "(unnamed)";
  }

  function treeCaseName(test) {
    return parseNodeId(test.testId).caseName || "(unnamed)";
  }

  function caseChineseTitle(test) {
    if (!test.caseTitle) return "";
    var wrap = document.createElement("div");
    wrap.innerHTML = test.caseTitle;
    var trigger = wrap.querySelector(".zframe-title-trigger");
    var text = trigger
      ? trigger.textContent
      : wrap.textContent || "";
    return String(text || "").trim();
  }

  function plainTitle(test) {
    if (test.caseId || test.caseTitle) {
      var wrap = document.createElement("div");
      wrap.innerHTML = test.caseTitle || "";
      var trigger = wrap.querySelector(".zframe-title-trigger");
      var text = trigger
        ? trigger.textContent
        : wrap.textContent || test.caseTitle || "";
      text = String(text || "").trim();
      if (test.caseId && text) return test.caseId + " · " + text;
      if (test.caseId) return test.caseId;
      if (text) return text;
    }
    return treeCaseLabel(test);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(ta);
      }
    });
  }

  function extractDetailHtml(test) {
    var wrap = document.createElement("div");
    wrap.innerHTML = test.caseTitle || "";
    var detail = wrap.querySelector(".zframe-case-detail");
    if (detail) return detail.outerHTML;
    var parts = [];
    if (test.caseId || test.priority || plainTitle(test)) {
      parts.push('<div class="zframe-case-detail">');
      parts.push('<div class="zframe-case-title">');
      if (test.caseId) parts.push("<strong>" + escapeHtml(test.caseId) + "</strong> ");
      if (test.priority) parts.push("<span>[" + escapeHtml(test.priority) + "]</span> ");
      parts.push(escapeHtml(plainTitle(test)));
      parts.push("</div></div>");
    }
    return parts.join("") || "<p>暂无步骤详情</p>";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function decodeHtmlEntities(s) {
    // Stock HTML reports store logs already entity-escaped (&quot; / &gt; / &#x27;).
    // Decode once before we escape for our own innerHTML insertion.
    var el = document.createElement("textarea");
    el.innerHTML = String(s || "");
    return el.value;
  }

  function formatLog(log) {
    var raw = decodeHtmlEntities(log || "No log output captured.");
    return String(raw)
      .split("\n")
      .map(function (line) {
        var esc = escapeHtml(line);
        if (/^E/.test(line)) {
          return '<span class="error">' + esc + "</span>";
        }
        return esc;
      })
      .join("\n");
  }

  function extrasHtml(extras) {
    if (!extras || !extras.length) return "";
    var chunks = ['<div class="zframe-extras">'];
    extras.forEach(function (extra) {
      var name = extra.name || extra.format_type || "extra";
      var content = extra.content || "";
      chunks.push("<div><strong>" + escapeHtml(name) + "</strong></div>");
      if (extra.format_type === "html") {
        chunks.push("<div>" + content + "</div>");
      } else {
        chunks.push("<pre>" + escapeHtml(typeof content === "string" ? content : JSON.stringify(content, null, 2)) + "</pre>");
      }
    });
    chunks.push("</div>");
    return chunks.join("");
  }

  function buildEnvBar(environment) {
    var env = environment || {};
    var keys = Object.keys(env);
    if (!keys.length) return null;

    var root = document.createElement("section");
    root.className = "zframe-env";

    // Prefer common env keys first; remaining keys still render alphabetically.
    var preferred = ["base_url", "product_version", "build_time", "env"];
    var labels = {
      base_url: "Base URL",
      product_version: "Product Version",
      build_time: "Build Time",
      env: "Env",
    };
    var ordered = preferred
      .filter(function (k) {
        return Object.prototype.hasOwnProperty.call(env, k);
      })
      .concat(
        keys.filter(function (k) {
          return preferred.indexOf(k) < 0;
        }).sort()
      );

    ordered.forEach(function (key) {
      var value = env[key];
      var text =
        value == null
          ? ""
          : typeof value === "object"
            ? JSON.stringify(value)
            : String(value);
      var item = document.createElement("div");
      item.className = "zframe-env__item";
      var label = labels[key] || key;
      var valueHtml;
      if (key === "base_url" && /^https?:\/\//i.test(text)) {
        valueHtml =
          '<a href="' +
          escapeHtml(text) +
          '" target="_blank" rel="noopener noreferrer">' +
          escapeHtml(text) +
          "</a>";
      } else {
        valueHtml = escapeHtml(text);
      }
      item.innerHTML =
        '<div class="zframe-env__label">' +
        escapeHtml(label) +
        '</div><div class="zframe-env__value">' +
        valueHtml +
        "</div>";
      root.appendChild(item);
    });
    return root;
  }

  function buildOverview(counts) {
    var root = document.createElement("section");
    root.className = "zframe-overview";
    STAT_META.forEach(function (meta) {
      var n = counts[meta.key] || 0;
      var card = document.createElement("div");
      card.className = "zframe-stat zframe-stat--" + meta.key;
      card.innerHTML =
        '<div class="zframe-stat__icon" aria-hidden="true">' +
        meta.icon +
        "</div>" +
        '<div class="zframe-stat__body">' +
        '<div class="zframe-stat__value">' +
        n +
        "</div>" +
        '<div class="zframe-stat__label">' +
        meta.label +
        "</div></div>";
      root.appendChild(card);
    });
    return root;
  }

  function groupTests(tests) {
    var byResult = {};
    var order = RESULT_ORDER.slice();
    RESULT_ORDER.forEach(function (r) {
      byResult[r] = {};
      KIND_ORDER.forEach(function (k) {
        byResult[r][k] = [];
      });
    });
    tests.forEach(function (t) {
      var r = t._result;
      if (!byResult[r]) {
        byResult[r] = { E2E: [], API: [], Other: [] };
        order.push(r);
      }
      var kind = t._kind;
      if (!byResult[r][kind]) byResult[r][kind] = [];
      byResult[r][kind].push(t);
    });
    byResult._order = order;
    return byResult;
  }

  function makeToggle(label, count, levelClass) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "zframe-tree-toggle" + (levelClass ? " " + levelClass : "");
    btn.innerHTML =
      '<span class="zframe-tree-toggle__chevron">▼</span>' +
      "<span>" +
      escapeHtml(label) +
      '</span><span class="zframe-tree-badge">' +
      count +
      "</span>";
    return btn;
  }

  function buildTree(tests, onSelect) {
    var aside = document.createElement("aside");
    aside.className = "zframe-case-tree";
    var grouped = groupTests(tests);

    (grouped._order || RESULT_ORDER).forEach(function (result) {
      if (result === "_order") return;
      var kinds = grouped[result];
      if (!kinds) return;
      var total = KIND_ORDER.reduce(function (sum, k) {
        return sum + (kinds[k] ? kinds[k].length : 0);
      }, 0);
      if (!total) return;

      var group = document.createElement("div");
      group.className = "zframe-tree-group";
      // Expand failed/error by default; collapse passed.
      if (result === "passed" || result === "skipped") {
        group.classList.add("is-collapsed");
      }

      var toggle = makeToggle(RESULT_LABEL[result] || result, total);
      toggle.addEventListener("click", function () {
        group.classList.toggle("is-collapsed");
      });
      group.appendChild(toggle);

      var children = document.createElement("div");
      children.className = "zframe-tree-children";

      KIND_ORDER.forEach(function (kind) {
        var list = kinds[kind] || [];
        if (!list.length) return;
        var kindNode = document.createElement("div");
        kindNode.className = "zframe-tree-kind is-collapsed";
        var kindToggle = makeToggle(kind, list.length);
        var kindChildren = document.createElement("div");
        kindChildren.className = "zframe-tree-children";
        kindToggle.addEventListener("click", function () {
          kindNode.classList.toggle("is-collapsed");
        });
        kindNode.appendChild(kindToggle);

        list.forEach(function (test) {
          var row = document.createElement("div");
          row.className = "zframe-tree-case";
          row.dataset.uid = test._uid;

          var label = treeCaseLabel(test);
          var cnTitle = caseChineseTitle(test);
          var main = document.createElement("button");
          main.type = "button";
          main.className = "zframe-tree-case__main";
          if (cnTitle) {
            main.setAttribute("aria-label", label + "，" + cnTitle);
            row.classList.add("has-tip");
          }
          main.innerHTML =
            '<span class="zframe-tree-case__status ' +
            escapeHtml(test._result) +
            '"></span>' +
            '<span class="zframe-tree-case__meta">' +
            '<div class="zframe-tree-case__title">' +
            escapeHtml(label) +
            "</div></span>";

          var durationText = test.duration ? String(test.duration).trim() : "";
          var durationEl = null;
          if (durationText) {
            durationEl = document.createElement("span");
            durationEl.className = "zframe-tree-case__duration";
            durationEl.textContent = durationText;
            durationEl.title = "执行耗时";
          }

          var copyBtn = document.createElement("button");
          copyBtn.type = "button";
          copyBtn.className = "zframe-tree-case__copy";
          copyBtn.title = "复制用例名";
          copyBtn.setAttribute("aria-label", "复制用例名");
          copyBtn.innerHTML =
            '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">' +
            '<rect x="5" y="5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/>' +
            '<path d="M3 10.5V3.5A1.5 1.5 0 0 1 4.5 2H10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>' +
            "</svg>";

          main.addEventListener("click", function () {
            aside.querySelectorAll(".zframe-tree-case.is-selected").forEach(function (el) {
              el.classList.remove("is-selected");
            });
            row.classList.add("is-selected");
            var kindEl = row.closest(".zframe-tree-kind");
            var groupEl = row.closest(".zframe-tree-group");
            if (kindEl) kindEl.classList.remove("is-collapsed");
            if (groupEl) groupEl.classList.remove("is-collapsed");
            onSelect(test);
          });
          copyBtn.addEventListener("click", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var name = treeCaseName(test);
            copyText(name).then(
              function () {
                copyBtn.classList.add("is-copied");
                copyBtn.title = "已复制";
                setTimeout(function () {
                  copyBtn.classList.remove("is-copied");
                  copyBtn.title = "复制用例名";
                }, 1200);
              },
              function () {
                copyBtn.title = "复制失败";
              }
            );
          });

          row.appendChild(main);
          if (durationEl) row.appendChild(durationEl);
          row.appendChild(copyBtn);
          if (cnTitle) {
            var tip = document.createElement("div");
            tip.className = "zframe-tree-case__tip";
            tip.setAttribute("role", "tooltip");
            tip.textContent = cnTitle;
            row.appendChild(tip);
          }
          kindChildren.appendChild(row);
        });

        kindNode.appendChild(kindChildren);
        children.appendChild(kindNode);
      });

      group.appendChild(children);
      aside.appendChild(group);
    });

    return aside;
  }

  function buildDetailPane() {
    var pane = document.createElement("div");
    pane.className = "zframe-detail-pane";
    pane.innerHTML =
      '<div class="zframe-detail-empty">请选择左侧用例查看步骤与日志</div>' +
      '<div class="zframe-detail-steps" hidden>' +
      '<button type="button" class="zframe-panel-head zframe-panel-head--toggle" data-action="toggle-steps" aria-expanded="true">' +
      '<span class="zframe-panel-head__title">用例步骤详情</span>' +
      '<span class="zframe-panel-head__hint" data-role="steps-hint">折叠</span>' +
      "</button>" +
      '<div class="zframe-panel-body" data-role="steps"></div>' +
      "</div>" +
      '<div class="zframe-detail-log" hidden>' +
      '<div class="zframe-panel-head"><span class="zframe-panel-head__title">用例执行日志</span></div>' +
      '<div class="zframe-panel-body" data-role="log"></div>' +
      "</div>";

    var stepsWrap = pane.querySelector(".zframe-detail-steps");
    var toggleBtn = pane.querySelector('[data-action="toggle-steps"]');
    var stepsHint = pane.querySelector('[data-role="steps-hint"]');
    toggleBtn.addEventListener("click", function () {
      var collapsed = stepsWrap.classList.toggle("is-collapsed");
      stepsHint.textContent = collapsed ? "展开" : "折叠";
      toggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });

    pane.showTest = function (test) {
      pane.querySelector(".zframe-detail-empty").hidden = true;
      stepsWrap.hidden = false;
      pane.querySelector(".zframe-detail-log").hidden = false;
      // Reset collapse when switching cases so long E2E steps stay reachable.
      stepsWrap.classList.remove("is-collapsed");
      stepsHint.textContent = "折叠";
      toggleBtn.setAttribute("aria-expanded", "true");
      pane.querySelector('[data-role="steps"]').innerHTML = extractDetailHtml(test);
      pane.querySelector('[data-role="log"]').innerHTML =
        formatLog(test.log) + extrasHtml(test.extras);
    };

    return pane;
  }

  function mount(blob) {
    var host = document.getElementById("zframe-report-ui");
    if (!host) return;
    host.innerHTML = "";

    var tests = flattenTests(blob);
    var counts = countByResult(tests);
    var envBar = buildEnvBar(blob.environment);
    if (envBar) host.appendChild(envBar);
    host.appendChild(buildOverview(counts));

    var layout = document.createElement("section");
    layout.className = "zframe-detail-layout";
    var detail = buildDetailPane();
    var tree = buildTree(tests, function (test) {
      detail.showTest(test);
    });
    layout.appendChild(tree);
    layout.appendChild(detail);
    host.appendChild(layout);

    document.body.classList.add("zframe-enhanced");

    // Auto-select first failed/error case when present.
    var preferred =
      tests.find(function (t) {
        return t._result === "failed" || t._result === "error";
      }) || tests[0];
    if (preferred) {
      var row = Array.prototype.find.call(
        tree.querySelectorAll(".zframe-tree-case"),
        function (el) {
          return el.dataset.uid === preferred._uid;
        }
      );
      var mainBtn = row && row.querySelector(".zframe-tree-case__main");
      if (mainBtn) mainBtn.click();
    }
  }

  function boot() {
    var host = document.getElementById("zframe-report-ui");
    var container = document.getElementById("data-container");
    if (!container) {
      if (host) {
        host.innerHTML =
          '<p class="zframe-detail-empty">未找到报告数据（data-container）</p>';
      }
      return;
    }
    var blob = decodeBlob(container.getAttribute("data-jsonblob"));
    if (!blob) {
      if (host) {
        host.innerHTML =
          '<p class="zframe-detail-empty">报告数据解析失败，请打开控制台查看错误</p>';
      }
      return;
    }
    try {
      mount(blob);
    } catch (err) {
      console.error("zframe report: mount failed", err);
      if (host) {
        host.innerHTML =
          '<p class="zframe-detail-empty">报告 UI 渲染失败：' +
          String(err && err.message ? err.message : err) +
          "</p>";
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    // Defer one tick so the stock report renderer finishes first.
    setTimeout(boot, 0);
  }
})();
