"use strict";

function practiceResultTitle(session) {
    const when = formatSessionTime(session.ended_at || session.started_at || "");
    const topic = session.topic ? " · " + session.topic : "";
    return when + topic;
}

function practiceSessionDetails(session) {
    const details = document.createElement("details");
    details.className = "topic-box";

    const summary = document.createElement("summary");
    const name = document.createElement("span");
    name.className = "topic-name";
    name.textContent = practiceResultTitle(session);
    const meta = document.createElement("span");
    meta.className = "topic-meta";
    meta.textContent = practiceSummaryText(session);
    summary.appendChild(name);
    summary.appendChild(meta);
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "topic-body";
    const hint = document.createElement("p");
    hint.className = "muted";
    hint.textContent = "Loading...";
    body.appendChild(hint);
    details.appendChild(body);

    let loaded = false;
    details.addEventListener("toggle", async () => {
        if (!details.open || loaded) return;
        loaded = true;
        try {
            const detail = await api("/api/admin/practice-sessions/" + session.id);
            body.replaceChildren();
            const list = document.createElement("ul");
            list.className = "question-list";
            (detail.attempts || []).forEach((attempt) => {
                list.appendChild(sessionAttemptItem(attempt));
            });
            if (!detail.attempts || !detail.attempts.length) {
                const empty = document.createElement("p");
                empty.className = "muted";
                empty.textContent = "No answers recorded in this run.";
                body.appendChild(empty);
            } else {
                body.appendChild(list);
            }
            body.appendChild(
                makeButton("Delete this run", "no", () => deletePracticeResult(session.id))
            );
        } catch (err) {
            hint.textContent = err.message;
            loaded = false;
        }
    });
    return details;
}

async function loadPracticeResults() {
    const box = el("practice-results-list");
    try {
        const payload = await api("/api/admin/practice-sessions");
        box.replaceChildren();
        const sessions = payload.sessions || [];
        el("practice-results-empty").hidden = sessions.length > 0;

        const groups = new Map();
        sessions.forEach((session) => {
            const displayName = (session.name || "Someone").trim() || "Someone";
            const key = displayName.toLocaleLowerCase();
            if (!groups.has(key)) groups.set(key, { name: displayName, sessions: [] });
            groups.get(key).sessions.push(session);
        });

        const sessionTime = (session) =>
            new Date(session.ended_at || session.started_at || 0).getTime() || 0;
        const orderedGroups = Array.from(groups.values()).sort((a, b) =>
            a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
        );

        orderedGroups.forEach((group) => {
            group.sessions.sort((a, b) => sessionTime(b) - sessionTime(a));
            const details = document.createElement("details");
            details.className = "topic-box practice-name-group";

            const summary = document.createElement("summary");
            const name = document.createElement("span");
            name.className = "topic-name";
            name.textContent = group.name;
            const meta = document.createElement("span");
            meta.className = "topic-meta";
            meta.textContent =
                group.sessions.length +
                (group.sessions.length === 1 ? " practice run" : " practice runs");
            summary.appendChild(name);
            summary.appendChild(meta);
            details.appendChild(summary);

            const body = document.createElement("div");
            body.className = "topic-body";
            const runs = document.createElement("div");
            runs.className = "accordion";
            group.sessions.forEach((session) => {
                runs.appendChild(practiceSessionDetails(session));
            });
            body.appendChild(runs);
            details.appendChild(body);
            box.appendChild(details);
        });
    } catch (err) {
        showError(err.message);
    }
}

async function deletePracticeResult(sessionId) {
    const first = await confirmAction({
        title: "Delete this practice run?",
        message: "Every recorded answer in this run will be removed. Questions and the squadron results are kept.",
        confirmLabel: "Continue",
    });
    if (!first) return;
    const second = await confirmAction({
        title: "Delete this practice run permanently?",
        message: "This cannot be undone.",
        confirmLabel: "Delete permanently",
    });
    if (!second) return;
    try {
        const payload = await api("/api/admin/practice-sessions/" + sessionId + "/delete", {
            method: "POST",
            body: { confirm: true },
        });
        showOk(payload.message || "That practice run has been deleted.");
        loadPracticeResults();
    } catch (err) {
        showError(err.message);
    }
}

function chip(label, className) {
    const span = document.createElement("span");
    span.className = "chip " + className;
    span.textContent = label;
    return span;
}

function makeButton(label, className, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "small-btn " + className;
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
}

function questionListItem(question, options = {}) {
    const item = document.createElement("li");

    const text = document.createElement("p");
    text.className = "q-text";
    text.textContent = question.question_text;
    item.appendChild(text);

    if (question.answer_text && options.showAnswer) {
        const answer = document.createElement("p");
        answer.className = "q-text muted";
        answer.textContent = "Answer: " + question.answer_text;
        item.appendChild(answer);
    }

    const meta = document.createElement("div");
    meta.className = "q-meta";
    if (question.topic) meta.appendChild(chip(question.topic, ""));
    if (question.archived_at) {
        meta.appendChild(chip("archived", "chip-archived"));
    } else if (question.status) {
        meta.appendChild(chip(question.status, "chip-" + question.status));
    }
    if (question.submitted_by) {
        meta.appendChild(chip("from " + question.submitted_by, ""));
    }
    if (question.outdated) {
        meta.appendChild(chip("may go out of date", "chip-pending"));
    }
    if (question.needs_review) meta.appendChild(chip("needs human review", "chip-rejected"));
    if (options.asked !== undefined) {
        meta.appendChild(
            chip(
                "asked " +
                    options.asked +
                    ", right " +
                    (options.correct || 0) +
                    ", wrong " +
                    (options.incorrect || 0),
                ""
            )
        );
    }
    if (options.extra) {
        meta.appendChild(chip(options.extra, ""));
    }
    item.appendChild(meta);

    if (options.actions) {
        const actions = document.createElement("div");
        actions.className = "q-actions";
        options.actions(question, actions);
        item.appendChild(actions);
    }
    return item;
}

// action buttons shared by the bank and the review queue, so the two never drift
// the actions shown against every question in the bank
function questionActions(question) {
    return (_item, actions) => {
        if (question.archived_at) {
            actions.appendChild(
                makeButton("Restore to quiz", "ok", () => restoreQuestion(question.id))
            );
        } else if (question.status === "pending" || question.status === "rejected") {
            actions.appendChild(
                makeButton("Accept", "ok", () => reviewFromBank(question.id, "approve"))
            );
        } else if (question.status === "approved") {
            actions.appendChild(
                makeButton("Remove from quiz", "no", () => reviewFromBank(question.id, "reject"))
            );
            actions.appendChild(
                makeButton("Archive", "no", () => archiveQuestion(question.id))
            );
        }
        if (!question.archived_at) {
            if (question.outdated) {
                actions.appendChild(
                    makeButton("Remove flag", "", () => tagOutdated(question.id, false))
                );
            } else {
                actions.appendChild(
                    makeButton("Flag out of date", "", () => tagOutdated(question.id, true))
                );
            }
        }
        actions.appendChild(makeButton("Edit", "", () => editQuestion(question)));
    };
}

async function loadChecks() {
    try {
        const [stalePayload, reportPayload] = await Promise.all([
            api("/api/admin/stale"), api("/api/admin/reports?status=pending&limit=5000"),
        ]);
        applyIdentity({ counts: stalePayload.counts, stale_count: stalePayload.stale_count,
            report_count: reportPayload.report_count, needs_review_count: stalePayload.needs_review_count });
        const staleList = el("stale-list");
        const reportList = el("reports-list");
        staleList.replaceChildren();
        reportList.replaceChildren();
        const staleQuestions = stalePayload.questions || [];
        const reports = reportPayload.reports || [];
        el("stale-empty").hidden = staleQuestions.length > 0;
        el("reports-empty").hidden = reports.length > 0;
        staleQuestions.forEach((q) => staleList.appendChild(questionListItem(q, {
            showAnswer: true,
            actions: (_item, actions) => {
                actions.appendChild(makeButton("Remove flag", "", () => tagOutdated(q.id, false)));
                actions.appendChild(makeButton("Edit", "", () => editQuestion(q)));
            },
        })));
        reports.forEach((r) => reportList.appendChild(reportListItem(r, false)));
        loadResolvedReports();
    } catch (err) { showError(err.message); }
}

async function loadHumanReview() {
    const list = el("needs-review-list");
    try {
        const payload = await api("/api/admin/stale");
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count,
            needs_review_count: payload.needs_review_count, report_count: payload.report_count });
        list.replaceChildren();
        const questions = payload.review_questions || [];
        el("needs-review-empty").hidden = questions.length > 0;
        questions.forEach((question) => {
            const item = questionListItem(question, {
                showAnswer: true,
                actions: (_item, actions) => {
                    actions.appendChild(makeButton("Edit and clear review flag", "ok", () => editQuestion(question)));
                    actions.appendChild(makeButton("Clear flag", "", () => tagNeedsReview(question.id, false)));
                },
            });
            if (question.ai_question_text) {
                const suggestion = document.createElement("p");
                suggestion.className = "q-text muted";
                suggestion.textContent = "Previous AI suggestion (not applied): " + question.ai_question_text + " — " + (question.ai_answer_text || "(no answer)");
                item.insertBefore(suggestion, item.querySelector(".q-actions"));
            }
            list.appendChild(item);
        });
    } catch (err) { showError(err.message); }
}

async function loadAiReview() {
    const list = el("ai-review-list");
    try {
        const payload = await api("/api/admin/stale");
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count,
            needs_review_count: payload.needs_review_count, ai_pending_count: payload.ai_pending_count,
            report_count: payload.report_count });
        list.replaceChildren();
        const questions = payload.ai_questions || [];
        el("ai-review-empty").hidden = questions.length > 0;
        questions.forEach((question) => {
            const item = questionListItem(question, { showAnswer: true });
            const suggestion = document.createElement("p");
            suggestion.className = "q-text";
            suggestion.textContent = "AI suggestion: " + question.ai_question_text + " — " + (question.ai_answer_text || "(no answer)");
            const topic = document.createElement("p");
            topic.className = "q-text muted";
            topic.textContent = "Suggested topic: " + question.ai_topic + (question.ai_reason ? " · " + question.ai_reason : "");
            item.insertBefore(suggestion, item.querySelector(".q-actions"));
            item.insertBefore(topic, item.querySelector(".q-actions"));
            const actions = item.querySelector(".q-actions") || document.createElement("div");
            if (!actions.parentNode) { actions.className = "q-actions"; item.appendChild(actions); }
            actions.appendChild(makeButton("Accept without future-update tag", "ok", () => acceptAiQuestion(question.id, false)));
            actions.appendChild(makeButton("Accept and mark for future update", "", () => acceptAiQuestion(question.id, true)));
            actions.appendChild(makeButton("Reject AI proposal", "no", () => rejectAiQuestion(question.id)));
            actions.appendChild(makeButton("Send to manual review", "", () => sendAiToHuman(question.id)));
            list.appendChild(item);
        });
    } catch (err) { showError(err.message); }
}

async function acceptAiQuestion(questionId, markForFutureUpdate) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/accept-ai", { method: "POST", body: { outdated: markForFutureUpdate } });
        applyIdentity(payload);
        showOk(markForFutureUpdate ? "AI change accepted and tagged for future review." : "AI change accepted without a future-update tag.");
        loadAiReview();
        loadBank();
    } catch (err) { showError(err.message); }
}

async function rejectAiQuestion(questionId) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/reject-ai", { method: "POST", body: {} });
        applyIdentity(payload);
        showOk("AI proposal rejected. The current question was kept unchanged.");
        loadAiReview();
        loadBank();
    } catch (err) { showError(err.message); }
}

async function sendAiToHuman(questionId) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/send-to-human", { method: "POST", body: {} });
        applyIdentity(payload);
        showOk("Question sent to the manual human-review queue; its original text is unchanged.");
        loadAiReview();
        loadHumanReview();
        loadBank();
    } catch (err) { showError(err.message); }
}

function showPrompt(text) {
    const page = el("view-" + state.view);
    const panel = page.querySelector(".prompt-panel");
    const preview = panel.querySelector(".prompt-preview");
    preview.value = text;
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function copyPrompt() {
    const page = el("view-" + state.view);
    const preview = page.querySelector(".prompt-preview");
    try {
        await navigator.clipboard.writeText(preview.value);
        showOk("Prompt copied. Paste it into your AI tool.");
    } catch (err) {
        preview.focus();
        preview.select();
        showError("Clipboard access is unavailable. The prompt is selected; copy it manually.");
    }
}

async function makeChecksPrompt() {
    try {
        const [stalePayload, reportPayload] = await Promise.all([
            api("/api/admin/stale"), api("/api/admin/reports?status=pending&limit=5000"),
        ]);
        const byId = new Map();
        (stalePayload.questions || []).forEach((q) => byId.set(q.id, {
            id: q.id, reportIds: [], reportReasons: [], question: q.question_text,
            answer: q.answer_text, topic: q.topic, check: "future_update_flag",
        }));
        (reportPayload.reports || []).forEach((r) => {
            const q = byId.get(r.question_id) || {
                id: r.question_id, reportIds: [], reportReasons: [], question: r.question_text,
                answer: r.answer_text, topic: r.topic, check: "reported",
            };
            q.reportIds.push(r.id);
            q.reportReasons.push((r.reporter_name ? r.reporter_name + ": " : "") + (r.reason || "No details provided"));
            if (r.question_archived || r.question_missing) q.check = "archived_or_removed_report";
            if (q.check === "future_update_flag") q.check = "future_update_flag and reported";
            byId.set(r.question_id, q);
        });
        const items = [...byId.values()];
        if (!items.length) { showOk("There are no flagged questions or pending reports to include."); return; }
        const quote = (v) => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
        const rows = ["id,report_ids,check,report_reasons,question,answer,topic"].concat(items.map((q) =>
            [q.id, q.reportIds.join(";"), q.check, q.reportReasons.join(" | "), q.question, q.answer, q.topic].map(quote).join(",")
        )).join("\n");
        const prompt = "You are returning data to an algorithm that imports your CSV into a live Air Cadets quiz. Check every question against reliable current sources and consider the report details. Return only valid CSV with the exact header id,report_ids,action,question,answer,topic,reason and exactly one row for every input id. Preserve id and report_ids exactly; keep report_ids blank when blank. Use update only for a verified correction and provide the complete final question, answer and topic. Use flag when the current answer is correct but likely to change in future; repeat the current fields unchanged. Use review when uncertain or unable to verify; repeat all current fields unchanged so the question is sent to human review. Use ok when correct and stable. Use dismiss only for a reported question when no correction is needed. For archived_or_removed_report rows, use dismiss only. Never guess, omit rows, change wording for style, or add prose, Markdown or extra rows. Quote fields using standard CSV escaping.\n\nINPUT CSV:\n" + rows;
        showPrompt(prompt);
    } catch (err) { showError(err.message); }
}

async function tagNeedsReview(questionId, tagged) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/needs-review", {
            method: "POST", body: { tagged },
        });
        applyIdentity(payload);
        showOk(tagged ? "Question marked for human review." : "Human review flag cleared.");
        loadHumanReview();
        loadBank();
    } catch (err) { showError(err.message); }
}

async function tagOutdated(questionId, tagged) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/stale", {
            method: "POST",
            body: { tagged: tagged },
        });
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
        showOk(tagged ? "Tagged as possibly going out of date." : "Tag removed.");
        loadBank();
        if (state.view === "checks") loadChecks();
        else refreshAdminBadges();
    } catch (err) {
        showError(err.message);
    }
}

async function refreshAdminBadges() {
    if (!state.user || state.user.role !== "admin") return;
    try {
        const payload = await api("/api/admin/stale");
        applyIdentity({
            counts: payload.counts,
            stale_count: payload.stale_count,
            needs_review_count: payload.needs_review_count,
            ai_pending_count: payload.ai_pending_count,
            report_count: payload.report_count,
        });
    } catch (err) {
        // badges stay as they were; the stale view will report the error
    }
}

function reportListItem(report, handled) {
    const item = document.createElement("li");

    const text = document.createElement("p");
    text.className = "q-text";
    text.textContent = report.question_text || "(question removed)";
    item.appendChild(text);

    if (report.answer_text) {
        const answer = document.createElement("p");
        answer.className = "q-text muted";
        answer.textContent = "Answer: " + report.answer_text;
        item.appendChild(answer);
    }

    if (report.reason) {
        const reason = document.createElement("p");
        reason.className = "q-text muted";
        reason.textContent = "Report: " + report.reason;
        item.appendChild(reason);
    }

    const meta = document.createElement("div");
    meta.className = "q-meta";
    if (report.topic) meta.appendChild(chip(report.topic, ""));
    meta.appendChild(
        chip(
            report.status,
            report.status === "pending"
                ? "chip-pending"
                : report.status === "resolved"
                  ? "chip-approved"
                  : "chip-rejected"
        )
    );
    if (report.reporter_name) meta.appendChild(chip("from " + report.reporter_name, ""));
    if (report.created_at) meta.appendChild(chip(formatSessionTime(report.created_at), ""));
    item.appendChild(meta);

    if (!handled) {
        const actions = document.createElement("div");
        actions.className = "q-actions";
        actions.appendChild(
            makeButton("Mark fixed", "ok", () => resolveReport(report.id, "resolved"))
        );
        actions.appendChild(
            makeButton("Dismiss", "no", () => resolveReport(report.id, "dismissed"))
        );
        if (!report.question_missing && !report.question_archived) {
            actions.appendChild(
                makeButton("Edit", "", () =>
                    editQuestion({
                        id: report.question_id,
                        question_text: report.question_text,
                        answer_text: report.answer_text,
                        topic: report.topic,
                    })
                )
            );
        }
        item.appendChild(actions);
    }
    return item;
}

async function loadResolvedReports() {
    const box = el("reports-resolved-box");
    const list = el("reports-resolved-list");
    try {
        const payload = await api("/api/admin/reports?status=resolved");
        list.replaceChildren();
        const items = payload.reports || [];
        box.hidden = items.length === 0;
        el("reports-resolved-meta").textContent =
            items.length + (items.length === 1 ? " handled" : " handled");
        items.slice(0, 50).forEach((report) => {
            list.appendChild(reportListItem(report, true));
        });
    } catch (err) {
        // the pending list already loaded; leave the handled group as it was
    }
}

async function resolveReport(reportId, action) {
    try {
        const payload = await api("/api/admin/reports/" + reportId + "/resolve", {
            method: "POST",
            body: { action: action },
        });
        applyIdentity({
            counts: payload.counts,
            stale_count: payload.stale_count,
            report_count: payload.report_count,
        });
        showOk(action === "resolved" ? "Report marked fixed." : "Report dismissed.");
        if (state.view === "checks") loadChecks();
        else refreshAdminBadges();
    } catch (err) {
        showError(err.message);
    }
}

async function loadPending() {
    const list = el("review-list");
    try {
        const payload = await api("/api/admin/pending");
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
        list.replaceChildren();
        const items = payload.questions;
        el("review-empty").hidden = items.length > 0;
        el("review-summary").textContent =
            items.length === 0
                ? "All caught up."
                : items.length + " question(s) waiting for your review.";

        items.forEach((question) => {
            list.appendChild(
                questionListItem(question, {
                    showAnswer: true,
                    actions: (_item, actions) => {
                        actions.appendChild(
                            makeButton("Accept", "ok", () => review(question.id, "approve"))
                        );
                        actions.appendChild(
                            makeButton("Reject", "no", () => review(question.id, "reject"))
                        );
                        actions.appendChild(makeButton("Edit", "", () => editQuestion(question)));
                    },
                })
            );
        });    } catch (err) {
        showError(err.message);
    }
}

async function review(questionId, status) {
    clearBanners();
    try {
        const payload = await api(
            "/api/admin/questions/" + questionId + "/" + status,
            { method: "POST", body: {} }
        );
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
        showOk(status === "approve" ? "Question accepted." : "Question rejected.");
        await loadPending();
    } catch (err) {
        showError(err.message);
    }
}

async function renameTopic(topic, count) {
    const values = await askForValues({
        title: "Rename topic",
        hint:
            (count === 1 ? "1 question is" : count + " questions are") + ' on "' + topic +
            '". Renaming moves them all across. The questions themselves are not changed.',
        fields: [
            {
                id: "from",
                label: "Current topic",
                value: topic,
                readonly: true,
                note: "This is the topic being renamed.",
            },
            {
                id: "to",
                label: "New name",
                value: topic,
                maxlength: 80,
                list: "known-topics",
                placeholder: "Type a name or pick one",
                options: state.topics || [],
            },
        ],
        submitLabel: "Rename topic",
    });
    if (values === null) return;
    if (!values.to) {
        showError("A topic needs a name.");
        return;
    }
    try {
        const payload = await api("/api/admin/topics/rename", {
            method: "POST",
            body: { from: values.from, to: values.to },
        });
        showOk(
            (payload.moved === 1 ? "1 question moved" : payload.moved + " questions moved") +
                ' to "' + payload.to + '".'
        );
        // loadBank pulls the topic list back with it, so the filter and the
        // add-question topic list both pick up the new name
        await loadBank();
        renderSubmitTopicSelect();
        loadPending();
    } catch (err) {
        showError(err.message);
    }
}

async function editQuestion(question) {
    const values = await askForValues({
        title: "Edit question",
        fields: [
            {
                id: "question_text",
                label: "Question",
                value: question.question_text,
                rows: 3,
                maxlength: 2000,
            },
            {
                id: "answer_text",
                label: "Answer",
                value: question.answer_text || "",
                rows: 2,
                maxlength: 2000,
            },
            {
                id: "topic",
                label: "Topic",
                value: question.topic || "",
                maxlength: 80,
                list: "known-topics",
                placeholder: "Type a topic or pick one",
                options: state.topics || [],
            },
        ],
        submitLabel: "Save question",
    });
    if (values === null) return;
    if (!values.topic) {
        showError("A question needs a topic.");
        return;
    }
    try {
        await api("/api/admin/questions/" + question.id + "/edit", {
            method: "POST",
            body: values,
        });
        showOk("Question updated.");
        loadPending();
        loadBank();
        if (state.view === "checks") loadChecks();
        if (state.view === "human-review") loadHumanReview();
        else refreshAdminBadges();
    } catch (err) {
        showError(err.message);
    }
}

async function deleteQuestion(questionId) {
    const confirmed = await confirmAction({
        title: "Delete this question permanently?",
        message: "Its recorded attempts and quiz-history entries will also be removed.",
        confirmLabel: "Delete question",
    });
    if (!confirmed) return;
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/delete", {
            method: "POST",
            body: {},
        });
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
        showOk("Question deleted.");
        if (state.boardEditor?.question.id === questionId) closeBoardEditor();
        if (state.view === "board") {
            await loadQuestionBoard();
        } else {
            loadPending();
            loadBank();
            if (state.view === "checks") loadChecks();
            if (state.view === "human-review") loadHumanReview();
        }
    } catch (err) {
        showError(err.message);
    }
}

const BANK_GROUPS = [
    { value: "pending", label: "Pending" },
    { value: "approved", label: "Accepted" },
    { value: "rejected", label: "Rejected" },
    { value: "archived", label: "Archived" },
];

// remember which topic groups the admin has opened, so accepting or deleting
// a question does not collapse everything they are working through
const openBankGroups = new Set();

function bankTopicGroup(status, topic, items) {
    const key = status + "::" + topic;
    const box = document.createElement("details");
    box.className = "topic-box";
    box.open = openBankGroups.has(key);
    box.addEventListener("toggle", () => {
        if (box.open) openBankGroups.add(key);
        else openBankGroups.delete(key);
    });

    const summary = document.createElement("summary");
    const name = document.createElement("span");
    name.className = "topic-name";
    name.textContent = topic;
    const meta = document.createElement("span");
    meta.className = "topic-meta";
    meta.textContent = items.length + (items.length === 1 ? " question" : " questions");
    summary.appendChild(name);
    summary.appendChild(meta);
    if (state.user && state.user.role === "admin") {
        // a button inside summary would otherwise toggle the group open or closed
        const rename = makeButton("Rename", "", () => renameTopic(topic, items.length));
        rename.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
        });
        summary.appendChild(rename);
    }
    box.appendChild(summary);

    const body = document.createElement("div");
    body.className = "topic-body";
    const list = document.createElement("ul");
    list.className = "question-list";
    items.forEach((question) => {
        list.appendChild(
            questionListItem(question, {
                showAnswer: true,
                actions: questionActions(question),
            })
        );
    });
    body.appendChild(list);
    box.appendChild(body);
    return box;
}

function bankStatusGroup(group, items) {
    const section = document.createElement("section");
    section.className = "bank-group";
    section.dataset.status = group.value;

    const title = document.createElement("h3");
    title.className = "section-label";
    title.textContent = group.label;
    const count = document.createElement("span");
    count.className = "muted";
    count.textContent = " (" + items.length + ")";
    title.appendChild(count);
    section.appendChild(title);

    if (!items.length) {
        const empty = document.createElement("p");
        empty.className = "muted";
        empty.textContent = "Nothing here.";
        section.appendChild(empty);
        return section;
    }

    // group the questions inside this status by their theme, in alphabetical order
    const byTopic = new Map();
    items.forEach((question) => {
        const topic = question.topic || "Uncategorised";
        if (!byTopic.has(topic)) byTopic.set(topic, []);
        byTopic.get(topic).push(question);
    });
    Array.from(byTopic.keys())
        .sort((a, b) => a.localeCompare(b))
        .forEach((topic) => {
            section.appendChild(bankTopicGroup(group.value, topic, byTopic.get(topic)));
        });
    return section;
}

const BOARD_COLUMNS = [
    { id: "active", label: "Active" },
    { id: "time-sensitive", label: "Active · time sensitive" },
    { id: "reported", label: "Reported" },
    { id: "approval", label: "Approval" },
    { id: "archive", label: "Archive" },
];

function setMobileBoardCardExpanded(card, expanded) {
    card.classList.toggle("is-expanded", expanded);
    card.setAttribute("aria-expanded", expanded ? "true" : "false");
    const question = card.querySelector(".board-card-question")?.textContent || "Question";
    card.setAttribute("aria-label", expanded ? question + ". Question actions shown." : question + ". Tap to show question actions.");
}

function toggleMobileBoardCard(card) {
    if (!window.matchMedia("(max-width: 680px)").matches) return;
    const expanded = !card.classList.contains("is-expanded");
    document.querySelectorAll("#question-board .board-question-card.is-expanded").forEach((other) => {
        if (other !== card) setMobileBoardCardExpanded(other, false);
    });
    setMobileBoardCardExpanded(card, expanded);
}

function questionBoardCard(question) {
    const card = document.createElement("article");
    card.className = "board-question-card";
    card.draggable = !window.matchMedia("(max-width: 680px)").matches;
    card.tabIndex = 0;
    card.dataset.questionId = String(question.id);
    const isMobileBoard = window.matchMedia("(max-width: 680px)").matches;
    card.setAttribute("aria-label", isMobileBoard
        ? question.question_text + ". Tap to show question actions."
        : question.question_text + ". Drag to change state or open details.");
    card.setAttribute("aria-expanded", "false");
    const topic = document.createElement("span");
    topic.className = "board-card-topic";
    topic.textContent = question.topic || "Uncategorised";
    const text = document.createElement("p");
    text.className = "board-card-question";
    text.textContent = question.question_text;
    const answer = document.createElement("p");
    answer.className = "board-card-answer";
    answer.textContent = question.answer_text || "No answer provided";
    const mobileActions = document.createElement("div");
    mobileActions.className = "board-card-mobile-actions";
    const moveLabel = document.createElement("label");
    moveLabel.textContent = "Move to";
    const moveSelect = document.createElement("select");
    moveSelect.setAttribute("aria-label", "Move question to another board column");
    BOARD_COLUMNS.filter((column) => column.id !== "reported").forEach((column) => {
        if (column.id === question.board_state) return;
        const option = document.createElement("option");
        option.value = column.id;
        option.textContent = column.label;
        moveSelect.appendChild(option);
    });
    const moveButton = makeButton("Move", "", () => moveBoardQuestion(question.id, moveSelect.value));
    moveButton.classList.add("board-card-mobile-move");
    moveLabel.appendChild(moveSelect);
    const editButton = makeButton("Edit question", "", () => openBoardEditor(question, card));
    editButton.classList.add("board-card-mobile-edit");
    const deleteButton = makeButton("Delete question", "no", () => deleteQuestion(question.id));
    deleteButton.classList.add("board-card-mobile-delete");
    mobileActions.append(moveLabel, moveButton, editButton, deleteButton);
    card.append(topic, text, answer, mobileActions);
    card.addEventListener("click", (event) => {
        if (event.target.closest("button, input, select, textarea, label, a")) return;
        toggleMobileBoardCard(card);
    });
    card.addEventListener("dragstart", (event) => {
        state.boardDragged = { questionId: question.id, question, card };
        card.classList.add("dragging");
        event.dataTransfer.effectAllowed = "copyMove";
        const searchText = state.boardEditor?.card === card
            ? (card.querySelector("#board-edit-question")?.value || question.question_text)
            : question.question_text;
        const googleUrl = "https://www.google.com/search?q=" + encodeURIComponent(searchText);
        event.dataTransfer.setData("text/uri-list", googleUrl);
        event.dataTransfer.setData("text/plain", googleUrl);
        const link = document.createElement("a");
        link.href = googleUrl;
        link.textContent = searchText;
        event.dataTransfer.setData("text/html", link.outerHTML);
        event.dataTransfer.setDragImage(card, 28, 20);
    });
    card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        state.boardDragged = null;
        document.querySelectorAll(".question-board-column.is-over").forEach((column) => column.classList.remove("is-over"));
    });
    card.addEventListener("keydown", (event) => {
        if (window.matchMedia("(max-width: 680px)").matches && state.boardEditor?.card !== card &&
                event.target === card && ["Enter", " "].includes(event.key)) {
            event.preventDefault();
            toggleMobileBoardCard(card);
            return;
        }
        if (state.boardEditor?.card === card && event.target === card && ["ArrowLeft", "ArrowRight", "Enter"].includes(event.key)) {
            event.preventDefault();
            const destinations = BOARD_COLUMNS.map((item) => item.id).filter((item) =>
                item !== "reported" || state.boardEditor.originalState === "reported"
            );
            if (event.key === "Enter") {
                saveBoardEditorAndMove(state.boardEditor.keyboardTarget);
                return;
            }
            let index = destinations.indexOf(state.boardEditor.keyboardTarget);
            index = (index + (event.key === "ArrowRight" ? 1 : destinations.length - 1)) % destinations.length;
            state.boardEditor.keyboardTarget = destinations[index];
            card.querySelector(".board-editor-drag-instruction").textContent =
                "Keyboard destination: " + (BOARD_COLUMNS.find((item) => item.id === destinations[index])?.label || "column") + " · ←/→ then Enter to save";
            return;
        }
        if ((event.key === "Enter" || event.key === " ") && event.target === card) {
            event.preventDefault();
            openBoardEditor(question, card);
        }
    });
    return card;
}

function renderBoardReports(question) {
    const list = el("board-editor-reports");
    list.replaceChildren();
    if (!question.reports || !question.reports.length) {
        const empty = document.createElement("p");
        empty.className = "muted";
        empty.textContent = "No reports have been made for this question.";
        list.appendChild(empty);
        return;
    }
    const heading = document.createElement("p");
    heading.className = "board-editor-section-label";
    heading.textContent = "Reports and history";
    list.appendChild(heading);
    question.reports.forEach((report) => {
        const row = document.createElement("div");
        row.className = "board-report-row";
        const detail = document.createElement("p");
        const when = report.created_at ? new Date(report.created_at).toLocaleString() : "Date unknown";
        detail.textContent = (report.reporter_name || "Reporter") + " · " + when +
            (report.status === "pending" ? " · Open" : " · " + report.status);
        const reason = document.createElement("p");
        reason.textContent = report.reason || "No reason provided.";
        row.append(detail, reason);
        list.appendChild(row);
    });
    if (question.report_count && question.board_state === "reported") {
        const hint = document.createElement("p");
        hint.className = "board-editor-drag-hint";
        hint.textContent = "Drag this card to another column to close its open reports.";
        list.appendChild(hint);
    }
}

function renderBoardSuggestion(question) {
    const panel = el("board-editor-suggestion");
    panel.replaceChildren();
    panel.hidden = !question.ai_pending;
    if (!question.ai_pending) return;
    const heading = document.createElement("p");
    heading.className = "board-editor-section-label";
    heading.textContent = "Suggested update · approval required";
    const proposal = document.createElement("p");
    proposal.textContent = question.ai_question_text + " — " + (question.ai_answer_text || "No answer supplied") +
        (question.ai_topic ? " · Topic: " + question.ai_topic : "");
    const reason = document.createElement("p");
    reason.textContent = question.ai_reason || "Review the suggested question and answer before applying it.";
    panel.append(heading, proposal, reason);
}

function setBoardEditorState(question, card) {
    const labels = {
        active: "Active",
        "time-sensitive": "Active · time sensitive",
        reported: "Reported · paused",
        approval: "Approval",
        archive: "Archive",
    };
    el("board-editor-state").textContent = labels[question.board_state] || "Question";
    const actions = document.createElement("div");
    actions.className = "board-editor-actions";
    if (question.ai_pending) {
        actions.appendChild(makeButton("Reject proposed update", "no", () => rejectAiQuestionFromBoard(question.id)));
    }
    card.querySelector(".board-editor-actions").replaceChildren(actions);
}

function boardEditorTopicValue() {
    const select = el("board-edit-topic");
    if (!select) return "";
    if (select.value === NEW_TOPIC) {
        const input = el("board-edit-topic-new");
        return input ? input.value.trim() : "";
    }
    return select.value.trim();
}

function openBoardEditor(question, card, options = {}) {
    if (state.boardEditor && state.boardEditor.card === card) return;
    if (state.boardEditor) {
        showError("Drop the expanded card into a board column to save before editing another question.");
        return;
    }
    const source = card || document.querySelector('.board-question-card[data-question-id="' + question.id + '"]');
    const column = source ? source.closest(".question-board-column") : null;
    if (!source || (!column && !options.isNew)) return;
    const initialState = options.initialState || "active";
    state.boardEditor = {
        question,
        card: source,
        originalState: options.isNew ? initialState : question.board_state,
        originalColumn: column,
        originalHost: column ? source.closest(".board-column-cards") : null,
        isNew: Boolean(options.isNew),
        returnFocus: document.activeElement,
    };
    setBoardEditorControlsDisabled(true);
    el("board-editor-content").hidden = false;
    el("board-editor-drop").hidden = true;
    el("board-editor-dock").classList.add("open");
    el("board-editor-card-slot").appendChild(source);

    source.classList.add("board-question-card-expanded");
    const canDragCard = !window.matchMedia("(max-width: 680px)").matches;
    source.draggable = canDragCard;
    source.tabIndex = 0;
    source.setAttribute("aria-label", "Expanded question editor. Drag the card outside its text fields to save and move it. Use left and right arrows, then Enter, to choose a destination.");
    source.addEventListener("pointerdown", (event) => {
        const inEditorControl = event.target instanceof Element &&
            Boolean(event.target.closest("textarea, input, select, button, a, label"));
        source.draggable = canDragCard && !inEditorControl;
        if (inEditorControl) {
            const restoreCardDrag = () => {
                source.draggable = canDragCard;
                window.removeEventListener("pointerup", restoreCardDrag);
                window.removeEventListener("pointercancel", restoreCardDrag);
            };
            window.addEventListener("pointerup", restoreCardDrag);
            window.addEventListener("pointercancel", restoreCardDrag);
        }
    });
    source.replaceChildren();
    const header = document.createElement("header");
    header.className = "board-editor-card-header";
    const stateLabel = document.createElement("span");
    stateLabel.className = "eyebrow";
    stateLabel.id = "board-editor-state";
    const dragInstruction = document.createElement("span");
    dragInstruction.className = "board-editor-drag-instruction";
    dragInstruction.textContent = "Drag anywhere on this card to save · ←/→ then Enter to choose a column";
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "board-editor-cancel";
    cancelButton.textContent = "Cancel";
    cancelButton.addEventListener("click", cancelBoardEditor);
    state.boardEditor.keyboardTarget = options.isNew ? initialState : question.board_state;
    header.append(stateLabel, dragInstruction, cancelButton);

    const fields = document.createElement("div");
    fields.className = "board-editor-fields";
    const questionLabel = document.createElement("label");
    questionLabel.htmlFor = "board-edit-question";
    questionLabel.textContent = "Question";
    const questionInput = document.createElement("textarea");
    questionInput.id = "board-edit-question";
    questionInput.maxLength = 2000;
    questionInput.required = true;
    questionInput.value = options.isNew ? "" : question.question_text;
    const answerLabel = document.createElement("label");
    answerLabel.htmlFor = "board-edit-answer";
    answerLabel.textContent = "Answer";
    const answerInput = document.createElement("textarea");
    answerInput.id = "board-edit-answer";
    answerInput.maxLength = 2000;
    answerInput.value = options.isNew ? "" : (question.answer_text || "");
    const topicLabel = document.createElement("label");
    topicLabel.htmlFor = "board-edit-topic";
    topicLabel.textContent = "Topic";
    const topicSelect = document.createElement("select");
    topicSelect.id = "board-edit-topic";
    const availableTopics = [...new Set([...(state.topics || []), question.topic].filter(Boolean))];
    availableTopics.sort((a, b) => a.localeCompare(b));
    availableTopics.forEach((topic) => {
        const option = document.createElement("option");
        option.value = topic;
        option.textContent = topic;
        topicSelect.appendChild(option);
    });
    const newTopicOption = document.createElement("option");
    newTopicOption.value = NEW_TOPIC;
    newTopicOption.textContent = "+ Add a new topic...";
    topicSelect.appendChild(newTopicOption);
    topicSelect.value = question.topic || availableTopics[0] || "";
    topicSelect.required = true;
    const topicNewLabel = document.createElement("label");
    topicNewLabel.htmlFor = "board-edit-topic-new";
    topicNewLabel.textContent = "New topic";
    topicNewLabel.hidden = true;
    const topicNewInput = document.createElement("input");
    topicNewInput.type = "text";
    topicNewInput.id = "board-edit-topic-new";
    topicNewInput.maxLength = 80;
    topicNewInput.placeholder = "Name of the new topic";
    topicNewInput.hidden = true;
    const syncBoardTopicNew = () => {
        const isNew = topicSelect.value === NEW_TOPIC;
        topicNewLabel.hidden = !isNew;
        topicNewInput.hidden = !isNew;
        topicNewInput.required = isNew;
        if (isNew) topicNewInput.focus();
    };
    topicSelect.addEventListener("change", syncBoardTopicNew);
    fields.append(
        questionLabel, questionInput, answerLabel, answerInput,
        topicLabel, topicSelect, topicNewLabel, topicNewInput
    );
    [questionInput, answerInput, topicSelect, topicNewInput].forEach((control) => {
        control.draggable = false;
    });

    const details = document.createElement("div");
    details.className = "board-editor-details";
    const reports = document.createElement("div");
    reports.className = "board-editor-reports";
    reports.id = "board-editor-reports";
    const suggestion = document.createElement("div");
    suggestion.className = "board-editor-suggestion";
    suggestion.id = "board-editor-suggestion";
    suggestion.hidden = true;
    const actions = document.createElement("div");
    actions.className = "board-editor-actions";
    fields.appendChild(actions);
    const mobileSave = document.createElement("button");
    mobileSave.type = "button";
    mobileSave.className = "primary board-editor-mobile-save";
    mobileSave.textContent = "Save changes";
    mobileSave.addEventListener("click", () => saveBoardEditorAndMove(mobileDestination.value));
    const mobileDestinationLabel = document.createElement("label");
    mobileDestinationLabel.className = "board-editor-mobile-destination";
    mobileDestinationLabel.htmlFor = "board-edit-destination";
    mobileDestinationLabel.textContent = "Save to column";
    const mobileDestination = document.createElement("select");
    mobileDestination.id = "board-edit-destination";
    BOARD_COLUMNS.filter((column) => column.id !== "reported" || question.board_state === "reported").forEach((column) => {
        const option = document.createElement("option");
        option.value = column.id;
        option.textContent = column.label;
        mobileDestination.appendChild(option);
    });
    mobileDestination.value = options.isNew ? initialState : question.board_state;
    fields.append(mobileDestinationLabel, mobileDestination, mobileSave);
    [mobileDestination, mobileSave, cancelButton].forEach((control) => {
        control.draggable = false;
    });
    details.append(reports, suggestion);
    source.append(header, fields, details);
    setBoardEditorState(question, source);
    renderBoardReports(question);
    renderBoardSuggestion(question);
    el("board-topic").disabled = true;
    document.querySelector("#view-board .board-tools").inert = true;
    if (window.matchMedia("(max-width: 680px)").matches) {
        el("board-editor-dock").setAttribute("role", "dialog");
        el("board-editor-dock").setAttribute("aria-modal", "true");
        el("board-editor-dock").setAttribute("aria-label", options.isNew ? "Add a question" : "Edit question");
        source.tabIndex = -1;
        document.body.classList.add("board-editor-modal-open");
        el("question-board-scroll").inert = true;
        el("board-page-heading").inert = true;
        el("board-swipe-hint").inert = true;
        el("side-menu").inert = true;
        document.querySelector(".site-header").inert = true;
    }
    source.focus({ preventScroll: true });
    if (!window.matchMedia("(max-width: 680px)").matches) {
        el("board-editor-dock").scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    requestAnimationFrame(() => el("board-edit-question").focus({ preventScroll: true }));
}

async function cancelBoardEditor() {
    const editor = state.boardEditor;
    if (!editor) return;
    const isNew = editor.isNew;
    const changed = isNew ||
        el("board-edit-question").value.trim() !== editor.question.question_text ||
        el("board-edit-answer").value.trim() !== (editor.question.answer_text || "") ||
        boardEditorTopicValue() !== (editor.question.topic || "");
    if (changed) {
        const confirmed = await confirmAction({
            title: isNew ? "Discard this new question?" : "Discard unsaved changes?",
            message: "The changes in the editor will be lost.",
            confirmLabel: "Discard",
        });
        if (!confirmed) return;
    }
    closeBoardEditor();
}

function updateBoardColumnCount(columnState) {
    const column = document.querySelector('.question-board-column[data-board-state="' + columnState + '"]');
    if (!column) return;
    const count = column.querySelector('[data-count="' + columnState + '"]');
    if (count) count.textContent = String(column.querySelectorAll(".board-question-card").length);
}

function stageBoardEditorDrop(targetState) {
    const editor = state.boardEditor;
    if (!editor) return;
    const host = document.querySelector(
        '.question-board-column[data-board-state="' + targetState + '"] .board-column-cards'
    );
    if (!host) return;
    editor.dropPending = true;
    el("board-editor-content").hidden = true;
    el("board-editor-drop").hidden = false;
    const preview = questionBoardCard({
        ...editor.question,
        question_text: el("board-edit-question").value.trim() || editor.question.question_text,
        answer_text: el("board-edit-answer").value.trim(),
        topic: boardEditorTopicValue() || editor.question.topic,
        board_state: targetState,
    });
    preview.classList.add("board-card-pending");
    preview.draggable = false;
    preview.tabIndex = -1;
    preview.setAttribute("aria-hidden", "true");
    host.querySelector(".board-empty")?.remove();
    host.appendChild(preview);
    editor.optimisticCard = preview;
    updateBoardColumnCount(targetState);
}

function restoreBoardEditorAfterDrop() {
    const editor = state.boardEditor;
    if (!editor) return;
    editor.dropPending = false;
    if (editor.optimisticCard) {
        const host = editor.optimisticCard.parentElement;
        editor.optimisticCard.remove();
        editor.optimisticCard = null;
        if (host && !host.querySelector(".board-question-card")) {
            const empty = document.createElement("p");
            empty.className = "board-empty";
            empty.textContent = "No questions here.";
            host.appendChild(empty);
        }
        updateBoardColumnCount(
            host?.closest(".question-board-column")?.dataset.boardState
        );
    }
    el("board-editor-content").hidden = false;
    el("board-editor-drop").hidden = true;
}

function closeBoardEditor({ restoreCard = true } = {}) {
    if (!state.boardEditor) return;
    const editor = state.boardEditor;
    if (restoreCard && editor.originalHost) {
        const cleanCard = questionBoardCard(editor.question);
        editor.card.replaceWith(cleanCard);
        editor.originalHost.appendChild(cleanCard);
    } else {
        editor.card.remove();
    }
    state.boardEditor = null;
    el("board-editor-dock").classList.remove("open");
    el("board-editor-dock").removeAttribute("role");
    el("board-editor-dock").removeAttribute("aria-modal");
    el("board-editor-dock").setAttribute("aria-label", "Question editor");
    document.body.classList.remove("board-editor-modal-open");
    el("question-board-scroll").inert = false;
    el("board-page-heading").inert = false;
    el("board-swipe-hint").inert = false;
    el("side-menu").inert = false;
    document.querySelector(".site-header").inert = false;
    el("board-editor-content").hidden = true;
    el("board-editor-drop").hidden = false;
    el("board-topic").disabled = false;
    document.querySelector("#view-board .board-tools").inert = false;
    setBoardEditorControlsDisabled(false);
    const savedCard = document.querySelector('#question-board .board-question-card[data-question-id="' + editor.question.id + '"]');
    const returnTarget = savedCard || (editor.originalHost
        ? editor.originalHost.querySelector('.board-column-add')
        : document.querySelector('.question-board-column[data-board-state="' + editor.originalState + '"] .board-column-add'));
    (returnTarget || editor.returnFocus)?.focus({ preventScroll: true });
}

function setBoardEditorControlsDisabled(disabled) {
    el("board-new-question").hidden = disabled;
    el("board-import-open").hidden = disabled;
}

function openNewBoardEditor(initialState = "active") {
    if (state.boardEditor) {
        showError("Save or return the current question before adding another.");
        return;
    }
    const question = {
        id: "draft-" + Date.now(), question_text: "", answer_text: "",
        topic: state.topics?.[0] || "", board_state: initialState, status: "draft",
        reports: [], report_count: 0, ai_pending: false,
    };
    const card = questionBoardCard(question);
    openBoardEditor(question, card, { isNew: true, initialState });
}

async function loadQuestionBoard({ preserveEditor = false } = {}) {
    if (state.boardEditor && !preserveEditor) closeBoardEditor();
    const params = new URLSearchParams();
    const topic = el("board-topic").value;
    if (topic) params.set("topic", topic);
    try {
        const payload = await api("/api/admin/question-board" + (params.size ? "?" + params.toString() : ""));
        applyIdentity(payload);
        state.boardQuestions = payload.questions || [];
        const groups = new Map(BOARD_COLUMNS.map((column) => [column.id, []]));
        state.boardQuestions.forEach((question) => groups.get(question.board_state).push(question));
        BOARD_COLUMNS.forEach((column) => {
            const host = el("board-" + column.id);
            host.replaceChildren();
            const questions = groups.get(column.id) || [];
            el("question-board").querySelector('[data-count="' + column.id + '"]').textContent = String(questions.length);
            if (!questions.length) {
                const empty = document.createElement("p");
                empty.className = "board-empty";
                empty.textContent = "No questions here.";
                host.appendChild(empty);
            } else {
                questions.forEach((question) => host.appendChild(questionBoardCard(question)));
            }
        });
    } catch (err) {
        showError(err.message);
        return false;
    }
    return true;
}

async function moveBoardQuestion(questionId, targetState, skipConfirmation) {
    const question = state.boardQuestions.find((item) => item.id === questionId);
    if (!question || targetState === "reported") return;
    if (targetState === "archive" && question.status !== "approved" && !question.archived_at) {
        showError("Only accepted questions can be archived. Reject or delete this submission from its editor.");
        return;
    }
    if (!skipConfirmation && targetState === "archive" && !question.archived_at) {
        const confirmed = await confirmAction({
            title: "Archive this question?",
            message: "It will leave quizzes while its history is kept.",
            confirmLabel: "Archive",
            danger: false,
        });
        if (!confirmed) return;
    }
    if (!skipConfirmation && ["active", "time-sensitive"].includes(targetState) &&
            ["pending", "rejected"].includes(question.status)) {
        const confirmed = await confirmAction({
            title: "Approve this question?",
            message: "It will be added to quizzes.",
            confirmLabel: "Approve",
            danger: false,
        });
        if (!confirmed) return;
    }
    if (!skipConfirmation && ["active", "time-sensitive"].includes(targetState) && question.ai_pending) {
        const confirmed = await confirmAction({
            title: "Apply the proposed update?",
            message: "This question will return to quizzes.",
            confirmLabel: "Apply update",
            danger: false,
        });
        if (!confirmed) return;
    }
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/board-state", {
            method: "POST", body: { state: targetState },
        });
        applyIdentity(payload);
        showOk("Question moved to " + BOARD_COLUMNS.find((column) => column.id === payload.state)?.label + ".");
        if (state.boardEditor && state.boardEditor.question.id === questionId) closeBoardEditor();
        await loadQuestionBoard();
    } catch (err) { showError(err.message); }
}

async function saveBoardEditorAndMove(targetState, { fromDrop = false } = {}) {
    const editor = state.boardEditor;
    if (!editor) return;
    const question = editor.question;
    const originalState = editor.originalState;
    const fields = {
        question_text: el("board-edit-question").value.trim(),
        answer_text: el("board-edit-answer").value.trim(),
        topic: boardEditorTopicValue(),
    };
    if (!fields.question_text || !fields.topic || (editor.isNew && !fields.answer_text)) {
        showError("A question and topic are required; new questions also need an answer.");
        return;
    }
    if (editor.isNew) {
        if (targetState === "reported") { showError("A new question cannot be moved to Reported without a user report."); return; }
        if (fromDrop) stageBoardEditorDrop(targetState);
        try {
            const created = await api("/api/questions", { method: "POST", body: fields });
            question.id = created.id;
            question.question_text = fields.question_text;
            question.answer_text = fields.answer_text;
            question.topic = fields.topic;
            question.status = created.status;
            question.board_state = "active";
            editor.isNew = false;
            editor.originalState = "active";
            applyIdentity(created);
            if (targetState !== "active") {
                const moved = await api("/api/admin/questions/" + question.id + "/board-state", {
                    method: "POST", body: { state: targetState },
                });
                question.board_state = moved.state;
                applyIdentity(moved);
            }
            if (!await loadQuestionBoard({ preserveEditor: true })) {
                restoreBoardEditorAfterDrop();
                return;
            }
            closeBoardEditor({ restoreCard: false });
            showOk("New question added to " + (BOARD_COLUMNS.find((column) => column.id === targetState)?.label || "the board") + ".");
        } catch (err) {
            restoreBoardEditorAfterDrop();
            showError(err.message);
        }
        return;
    }
    const changed = fields.question_text !== question.question_text || fields.answer_text !== (question.answer_text || "") || fields.topic !== (question.topic || "");
    if (["active", "time-sensitive"].includes(targetState) &&
            ["pending", "rejected"].includes(question.status)) {
        const confirmed = await confirmAction({
            title: "Approve this question?",
            message: "It will be added to quizzes.",
            confirmLabel: "Approve",
            danger: false,
        });
        if (!confirmed) return;
    }
    if (["active", "time-sensitive"].includes(targetState) && question.ai_pending) {
        const confirmed = await confirmAction({
            title: "Apply the proposed update?",
            message: "This question will return to quizzes.",
            confirmLabel: "Apply update",
            danger: false,
        });
        if (!confirmed) return;
    }
    if (fromDrop) stageBoardEditorDrop(targetState);
    try {
        if (changed) await api("/api/admin/questions/" + question.id + "/edit", { method: "POST", body: fields });
        if (targetState !== "reported" && (targetState !== editor.originalState || changed || question.status === "pending" && targetState === "active")) {
            const payload = await api("/api/admin/questions/" + question.id + "/board-state", {
                method: "POST", body: { state: targetState },
            });
            applyIdentity(payload);
        }
        if (!await loadQuestionBoard({ preserveEditor: true })) {
            restoreBoardEditorAfterDrop();
            return;
        }
        closeBoardEditor({ restoreCard: false });
        const destination = BOARD_COLUMNS.find((column) => column.id === targetState)?.label || "its column";
        showOk(changed ? "Question details saved in " + destination + "." :
            targetState === originalState ? "Question returned to its previous column." : "Question moved to " + destination + ".");
    } catch (err) {
        restoreBoardEditorAfterDrop();
        showError(err.message);
    }
}

async function rejectBoardSubmission(questionId) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/reject", { method: "POST", body: {} });
        applyIdentity(payload);
        closeBoardEditor();
        showOk("Submission rejected and kept on the board.");
        await loadQuestionBoard();
    } catch (err) { showError(err.message); }
}

async function rejectAiQuestionFromBoard(questionId) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/reject-ai", { method: "POST", body: {} });
        applyIdentity(payload);
        closeBoardEditor();
        showOk("Suggested update rejected; the current question was kept.");
        await loadQuestionBoard();
    } catch (err) { showError(err.message); }
}

async function loadBank() {
    return loadQuestionBoard();
}

async function reviewFromBank(questionId, status) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/" + status, {
            method: "POST",
            body: {},
        });
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
        showOk("Updated.");
        loadBank();
    } catch (err) {
        showError(err.message);
    }
}

async function archiveQuestion(questionId) {
    const confirmed = await confirmAction({
        title: "Archive this question?",
        message: "It will leave the quiz, but its history will be kept.",
        confirmLabel: "Archive",
        danger: false,
    });
    if (!confirmed) {
        return;
    }
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/archive", {
            method: "POST",
            body: {},
        });
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
        showOk("Question archived. Its answer history has been kept.");
        await loadBank();
    } catch (err) {
        showError(err.message);
    }
}

async function restoreQuestion(questionId) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/restore", {
            method: "POST",
            body: {},
        });
        applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
        showOk("Question restored to the quiz with its previous history.");
        await loadBank();
    } catch (err) {
        showError(err.message);
    }
}

function statTile(value, label) {
    const stat = document.createElement("div");
    stat.className = "stat";
    const number = document.createElement("span");
    number.className = "stat-value";
    number.textContent = String(value);
    const caption = document.createElement("span");
    caption.className = "stat-label";
    caption.textContent = label;
    stat.appendChild(number);
    stat.appendChild(caption);
    return stat;
}

async function resetProgress() {
    const first = await confirmAction({
        title: "Delete all squadron progress?",
        message: "Every recorded correct, incorrect and skipped answer will be removed. Questions, staff/NCO accounts and the question bank are kept.",
        confirmLabel: "Continue",
    });
    if (!first) return;
    const second = await confirmAction({
        title: "Delete all recorded progress permanently?",
        message: "This cannot be undone.",
        confirmLabel: "Delete all progress",
    });
    if (!second) return;
    try {
        await api("/api/admin/reset-progress", { method: "POST", body: { confirm: true } });
        showOk("All progress has been deleted.");
        loadStats();
    } catch (err) {
        showError(err.message);
    }
}

// In-page replacement for window.confirm.
// Shows a password the admin asked to see, in a read only field they can copy.
function showPasswordOnce(username, password) {
    // shown the moment it is set and never again: nothing readable is kept
    return askForValues({
        title: "Password set for " + username,
        hint:
            "Copy it now. It is stored only as a hash, so this is the last time " +
            "it can be shown. If you lose it, set a new one.",
        fields: [
            {
                id: "shown",
                label: "Password",
                value: password,
                readonly: true,
                note: "Click to select, then copy. This cannot be shown again.",
            },
        ],
        submitLabel: "Done",
    });
}

function accuracyLabel(accuracy) {
    return accuracy === null ? "not asked yet" : accuracy + "% accuracy";
}

const SVG_NS = "http://www.w3.org/2000/svg";

function svgNode(name, attrs = {}, text = "") {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text) node.textContent = text;
    return node;
}

function trendDateLabel(isoDate) {
    return new Date(isoDate + "T12:00:00Z").toLocaleDateString(undefined, {
        day: "numeric", month: "short", timeZone: "UTC",
    });
}

function makeTrendSvg(label) {
    const svg = svgNode("svg", {
        viewBox: "0 0 720 280", role: "img", "aria-label": label,
        class: "trend-chart", focusable: "false",
    });
    return svg;
}

function renderVolumeChart(weeks, hostId = "trend-volume-chart", scope = "squadron") {
    const host = el(hostId);
    host.replaceChildren();
    const svg = makeTrendSvg("Stacked bar chart of correct, incorrect, and skipped " + scope + " answers for each of the last 12 weeks");
    const colors = { correct: "#4f8a56", incorrect: "#b45d53", skipped: "#9aaab3" };
    const maxValue = Math.max(1, ...weeks.map((week) => week.correct + week.incorrect + week.skipped));
    const left = 46, right = 704, top = 18, bottom = 226, chartHeight = bottom - top;
    const step = (right - left) / weeks.length;
    const barWidth = Math.min(30, step * .56);
    for (let tick = 0; tick <= 4; tick++) {
        const value = Math.ceil(maxValue * tick / 4);
        const y = bottom - chartHeight * tick / 4;
        svg.appendChild(svgNode("line", { x1: left, y1: y, x2: right, y2: y, class: "trend-gridline" }));
        svg.appendChild(svgNode("text", { x: left - 8, y: y + 4, "text-anchor": "end", class: "trend-axis-label" }, String(value)));
    }
    weeks.forEach((week, index) => {
        const x = left + step * (index + .5) - barWidth / 2;
        let y = bottom;
        ["correct", "incorrect", "skipped"].forEach((key) => {
            const height = chartHeight * week[key] / maxValue;
            if (height > 0) {
                y -= height;
                svg.appendChild(svgNode("rect", { x, y, width: barWidth, height, fill: colors[key], rx: 2 }));
            }
        });
        if (index % 2 === 0 || index === weeks.length - 1) {
            svg.appendChild(svgNode("text", {
                x: left + step * (index + .5), y: bottom + 22,
                "text-anchor": "middle", class: "trend-axis-label",
            }, trendDateLabel(week.week_start)));
        }
    });
    host.appendChild(svg);
    const legend = document.createElement("div");
    legend.className = "trend-legend";
    [["correct", "Correct"], ["incorrect", "Incorrect"], ["skipped", "Skipped"]].forEach(([key, title]) => {
        const item = document.createElement("span");
        const swatch = document.createElement("i");
        swatch.style.backgroundColor = colors[key];
        item.append(swatch, document.createTextNode(title));
        legend.appendChild(item);
    });
    host.appendChild(legend);
}

function renderAccuracyChart(weeks, minimumSample, hostId = "trend-accuracy-chart", scope = "squadron") {
    const host = el(hostId);
    host.replaceChildren();
    const eligible = weeks.filter((week) => week.scored >= minimumSample);
    if (!eligible.length) {
        const note = document.createElement("p");
        note.className = "trend-chart-note";
        note.textContent = "There are not yet enough weekly answers to show a reliable accuracy trend.";
        host.appendChild(note);
        return;
    }
    const svg = makeTrendSvg("Line chart of weekly " + scope + " accuracy for weeks with at least " + minimumSample + " scored answers");
    const left = 46, right = 704, top = 22, bottom = 226;
    const chartHeight = bottom - top;
    for (let tick = 0; tick <= 4; tick++) {
        const value = tick * 25;
        const y = bottom - chartHeight * value / 100;
        svg.appendChild(svgNode("line", { x1: left, y1: y, x2: right, y2: y, class: "trend-gridline" }));
        svg.appendChild(svgNode("text", { x: left - 8, y: y + 4, "text-anchor": "end", class: "trend-axis-label" }, value + "%"));
    }
    const step = (right - left) / Math.max(weeks.length - 1, 1);
    const points = eligible.map((week) => {
        const index = weeks.indexOf(week);
        return {
            index,
            x: left + step * index,
            y: bottom - chartHeight * week.accuracy / 100,
            week,
        };
    });
    points.slice(1).forEach((point, index) => {
        const previous = points[index];
        if (point.index === previous.index + 1) {
            svg.appendChild(svgNode("line", {
                x1: previous.x, y1: previous.y, x2: point.x, y2: point.y, class: "trend-line",
            }));
        }
    });
    points.forEach((point) => {
        svg.appendChild(svgNode("circle", { cx: point.x, cy: point.y, r: 5, class: "trend-point" }));
        svg.appendChild(svgNode("text", {
            x: point.x, y: point.y - 10, "text-anchor": "middle", class: "trend-value-label",
        }, point.week.accuracy + "%"));
    });
    weeks.forEach((week, index) => {
        if (index % 2 === 0 || index === weeks.length - 1) {
            svg.appendChild(svgNode("text", {
                x: left + step * index, y: bottom + 22,
                "text-anchor": "middle", class: "trend-axis-label",
            }, trendDateLabel(week.week_start)));
        }
    });
    host.appendChild(svg);
}

async function loadProgressTrends() {
    try {
        const payload = await api("/api/admin/progress-trends");
        const weeks = payload.weeks || [];
        const total = weeks.reduce((sum, week) => sum + week.correct + week.incorrect + week.skipped, 0);
        el("trends-empty").hidden = total > 0;
        el("trend-volume-chart").parentElement.hidden = total === 0;
        el("trend-accuracy-chart").parentElement.hidden = total === 0;
        if (total > 0) {
            renderVolumeChart(weeks);
            renderAccuracyChart(weeks, payload.minimum_sample || 5);
        }
    } catch (err) {
        showError(err.message);
    }
}

async function loadPracticeTrends() {
    try {
        const payload = await api("/api/admin/practice-trends");
        const weeks = payload.weeks || [];
        const total = weeks.reduce((sum, week) => sum + week.correct + week.incorrect + week.skipped, 0);
        el("practice-trends-empty").hidden = total > 0;
        el("practice-trend-volume-chart").parentElement.hidden = total === 0;
        el("practice-trend-accuracy-chart").parentElement.hidden = total === 0;
        if (total > 0) {
            renderVolumeChart(weeks, "practice-trend-volume-chart", "practice");
            renderAccuracyChart(
                weeks, payload.minimum_sample || 5,
                "practice-trend-accuracy-chart", "practice"
            );
        }
    } catch (err) {
        showError(err.message);
    }
}

async function loadWebsiteIssues() {
    const list = el("website-issues-list");
    const empty = el("website-issues-empty");
    list.replaceChildren();
    empty.hidden = true;
    try {
        const payload = await api("/api/admin/website-issues");
        const issues = payload.issues || [];
        empty.hidden = issues.length > 0;
        issues.forEach((issue) => {
            const item = document.createElement("li");
            const title = document.createElement("p");
            title.className = "q-text";
            title.textContent = issue.title;
            item.appendChild(title);

            const details = document.createElement("p");
            details.className = "q-text muted";
            details.textContent = issue.details;
            item.appendChild(details);

            const meta = document.createElement("div");
            meta.className = "q-meta";
            if (issue.created_at) meta.appendChild(chip(formatSessionTime(issue.created_at), ""));
            if (issue.page) meta.appendChild(chip("page: " + issue.page, ""));
            item.appendChild(meta);

            const actions = document.createElement("div");
            actions.className = "q-actions";
            actions.appendChild(makeButton("Delete report", "no", () => deleteWebsiteIssue(issue.id)));
            item.appendChild(actions);
            list.appendChild(item);
        });
    } catch (err) {
        showError(err.message);
    }
}

async function deleteWebsiteIssue(issueId) {
    const confirmed = await confirmAction({
        title: "Delete this website issue report?",
        message: "The report will be removed permanently.",
        confirmLabel: "Delete report",
    });
    if (!confirmed) return;
    try {
        await api("/api/admin/website-issues/" + issueId + "/delete", { method: "POST" });
        showOk("Website issue report deleted.");
        loadWebsiteIssues();
    } catch (err) {
        showError(err.message);
    }
}

function renderStats(payload, overallId, topicsId, emptyId, accuracyName) {
    const overallBox = el(overallId);
    const topicBox = el(topicsId);

    overallBox.replaceChildren();
    [
        [payload.overall.asked, "questions asked"],
        [payload.overall.correct, "correct"],
        [payload.overall.incorrect, "incorrect"],
        [payload.overall.skipped, "skipped"],
        [accuracyLabel(payload.overall.accuracy), accuracyName],
    ].forEach(([value, label]) => overallBox.appendChild(statTile(value, label)));

    const byTopic = new Map();
    payload.questions.forEach((question) => {
        if (!byTopic.has(question.topic)) byTopic.set(question.topic, []);
        byTopic.get(question.topic).push(question);
    });

    topicBox.replaceChildren();
    el(emptyId).hidden = payload.topics.length > 0;

    payload.topics.forEach((topic) => {
        const details = document.createElement("details");
        details.className = "topic-box";

        const summary = document.createElement("summary");
        const name = document.createElement("span");
        name.className = "topic-name";
        name.textContent = topic.topic;
        const meta = document.createElement("span");
        meta.className = "topic-meta";
        meta.textContent =
            topic.question_count +
            " question(s) · " +
            topic.asked +
            " asked · " +
            accuracyLabel(topic.accuracy);
        summary.appendChild(name);
        summary.appendChild(meta);
        details.appendChild(summary);

        const body = document.createElement("div");
        body.className = "topic-body";
        const list = document.createElement("ul");
        list.className = "question-list";
        (byTopic.get(topic.topic) || []).forEach((question) => {
            list.appendChild(
                questionListItem(question, {
                    asked: question.asked,
                    correct: question.correct,
                    incorrect: question.incorrect,
                    extra: accuracyLabel(question.accuracy),
                })
            );
        });
        body.appendChild(list);
        details.appendChild(body);
        topicBox.appendChild(details);
    });
}

async function loadStats() {
    try {
        const payload = await api("/api/stats");
        renderStats(payload, "overall-stats", "stats-topics", "stats-empty", "squadron accuracy");
    } catch (err) {
        showError(err.message);
    }
}

async function loadPracticeStats() {
    try {
        const payload = await api("/api/admin/practice-stats");
        renderStats(
            payload, "practice-overall-stats", "practice-stats-topics",
            "practice-stats-empty", "practice accuracy"
        );
    } catch (err) {
        showError(err.message);
    }
}

function sessionSummaryText(session) {
    const scored = session.correct + session.incorrect;
    const accuracy = scored ? Math.round((session.correct / scored) * 100) : 0;
    return (
        session.asked +
        " asked · " +
        session.correct +
        " correct · " +
        session.incorrect +
        " incorrect · " +
        session.skipped +
        " skipped · " +
        accuracy +
        "% accuracy"
    );
}

function formatSessionTime(value) {
    // the server stores UTC ("...+00:00"); render it in the browser's local
    // time so it matches the clock on the wall instead of showing UTC.
    if (!value) return "";
    const date = new Date(value);
    if (isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
    const pad = (n) => String(n).padStart(2, "0");
    return (
        date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
        " " + pad(date.getHours()) + ":" + pad(date.getMinutes())
    );
}

function sessionTitle(session) {
    const who = session.display_name || session.username || "Staff/NCO";
    const when = formatSessionTime(session.ended_at || session.started_at || "");
    const topic = session.topic ? " · " + session.topic : "";
    return who + " · " + when + topic;
}

function sessionAttemptItem(attempt) {
    const item = document.createElement("li");

    const text = document.createElement("p");
    text.className = "q-text";
    text.textContent = attempt.question_text || "(question removed)";
    item.appendChild(text);

    if (attempt.answer_text) {
        const answer = document.createElement("p");
        answer.className = "q-text muted";
        answer.textContent = "Answer: " + attempt.answer_text;
        item.appendChild(answer);
    }

    const meta = document.createElement("div");
    meta.className = "q-meta";
    if (attempt.topic) meta.appendChild(chip(attempt.topic, ""));
    const resultClass =
        attempt.result === "correct"
            ? "chip-approved"
            : attempt.result === "incorrect"
              ? "chip-rejected"
              : "chip-pending";
    meta.appendChild(chip(attempt.result, resultClass));
    item.appendChild(meta);
    return item;
}

async function loadSessions() {
    const box = el("sessions-list");
    try {
        const payload = await api("/api/admin/quiz-sessions");
        box.replaceChildren();
        const sessions = payload.sessions || [];
        el("sessions-empty").hidden = sessions.length > 0;
        sessions.forEach((session) => {
            const details = document.createElement("details");
            details.className = "topic-box";

            const summary = document.createElement("summary");
            const name = document.createElement("span");
            name.className = "topic-name";
            name.textContent = sessionTitle(session);
            const meta = document.createElement("span");
            meta.className = "topic-meta";
            meta.textContent = sessionSummaryText(session);
            summary.appendChild(name);
            summary.appendChild(meta);
            details.appendChild(summary);

            const body = document.createElement("div");
            body.className = "topic-body";
            const hint = document.createElement("p");
            hint.className = "muted";
            hint.textContent = "Loading...";
            body.appendChild(hint);
            details.appendChild(body);

            let loaded = false;
            details.addEventListener("toggle", async () => {
                if (!details.open || loaded) return;
                loaded = true;
                try {
                    const detail = await api("/api/admin/quiz-sessions/" + session.id);
                    body.replaceChildren();
                    const list = document.createElement("ul");
                    list.className = "question-list";
                    (detail.attempts || []).forEach((attempt) => {
                        list.appendChild(sessionAttemptItem(attempt));
                    });
                    if (!detail.attempts || !detail.attempts.length) {
                        const empty = document.createElement("p");
                        empty.className = "muted";
                        empty.textContent = "No answers recorded in this session.";
                        body.appendChild(empty);
                    } else {
                        body.appendChild(list);
                    }
                    body.appendChild(
                        makeButton("Delete this session", "no", () => deleteQuizSession(session.id))
                    );
                } catch (err) {
                    hint.textContent = err.message;
                    loaded = false;
                }
            });

            box.appendChild(details);
        });
    } catch (err) {
        showError(err.message);
    }
}

async function deleteQuizSession(sessionId) {
    const first = await confirmAction({
        title: "Delete this quiz session?",
        message: "Every recorded correct, incorrect and skipped answer in this session will be removed. Questions, staff/NCO accounts and the question bank are kept.",
        confirmLabel: "Continue",
    });
    if (!first) return;
    const second = await confirmAction({
        title: "Delete this quiz session permanently?",
        message: "This cannot be undone.",
        confirmLabel: "Delete permanently",
    });
    if (!second) return;
    try {
        const payload = await api("/api/admin/quiz-sessions/" + sessionId + "/delete", {
            method: "POST",
            body: { confirm: true },
        });
        showOk(payload.message || "That quiz session has been deleted.");
        loadSessions();
    } catch (err) {
        showError(err.message);
    }
}

async function setUserUsername(user) {
    const values = await askForValues({
        title: "Change username",
        hint: "For " + (user.display_name || user.username),
        fields: [
            {
                id: "username",
                label: "Username",
                value: user.username,
                maxlength: 32,
            },
        ],
        submitLabel: "Save username",
    });
    if (values === null || values.username === user.username) return;
    try {
        await api("/api/admin/users/" + user.id + "/username", {
            method: "POST",
            body: { username: values.username },
        });
        showOk("Username updated.");
        loadUsers();
    } catch (err) {
        showError(err.message);
    }
}

async function setUserPassword(user) {
    const values = await askForValues({
        title: "Set password",
        hint:
            "For " + (user.display_name || user.username) +
            ". This is the password they will use, and you can read it back here at any time.",
        fields: [
            {
                id: "password",
                label: "New password",
                type: "password",
                minlength: 8,
                maxlength: 200,
            },
            {
                id: "confirm",
                label: "Confirm new password",
                type: "password",
                minlength: 8,
                maxlength: 200,
            },
        ],
        submitLabel: "Set password",
    });
    if (values === null) return;
    if (values.password !== values.confirm) {
        showError("The two passwords do not match.");
        return;
    }
    try {
        const payload = await api("/api/admin/users/" + user.id + "/password", {
            method: "POST",
            body: { password: values.password },
        });
        showOk(payload.message || "Password updated.");
        loadUsers();
        await showPasswordOnce(payload.username || user.username, values.password);
    } catch (err) {
        showError(err.message);
    }
}

async function loadUsers() {
    const list = el("user-list");
    try {
        const payload = await api("/api/admin/users");
        list.replaceChildren();
        payload.users.forEach((user) => {
            const item = document.createElement("li");
            const text = document.createElement("p");
            text.className = "q-text";
            text.textContent = user.display_name + " (" + user.username + ")";
            item.appendChild(text);

            const meta = document.createElement("div");
            meta.className = "q-meta";
            meta.appendChild(chip(user.role, user.role === "admin" ? "chip-approved" : ""));
            meta.appendChild(chip(user.active ? "active" : "disabled", user.active ? "chip-approved" : "chip-rejected"));
            if (user.must_change) meta.appendChild(chip("must change password", "chip-pending"));
            item.appendChild(meta);

            const actions = document.createElement("div");
            actions.className = "q-actions";
            if (user.id !== state.user.id) {
                actions.appendChild(
                    makeButton("Username", "", () => setUserUsername(user))
                );
                actions.appendChild(
                    makeButton("Password", "", () => setUserPassword(user))
                );
                actions.appendChild(
                    makeButton(user.active ? "Disable" : "Enable", user.active ? "no" : "ok", () =>
                        setUserActive(user.id, !user.active)
                    )
                );
            }
            if (actions.children.length) item.appendChild(actions);
            list.appendChild(item);
        });
    } catch (err) {
        showError(err.message);
    }
}

async function setUserActive(userId, active) {
    try {
        await api("/api/admin/users/" + userId + "/active", {
            method: "POST",
            body: { active: active },
        });
        showOk(active ? "Account enabled." : "Account disabled.");
        loadUsers();
    } catch (err) {
        showError(err.message);
    }
}

function bindAdminEvents() {
    window.addEventListener("beforeunload", (event) => {
        if (!state.boardEditor) return;
        event.preventDefault();
        event.returnValue = "";
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && state.boardEditor && window.matchMedia("(max-width: 680px)").matches) {
            event.preventDefault();
            cancelBoardEditor();
            return;
        }
        if (state.boardEditor && window.matchMedia("(max-width: 680px)").matches && event.key === "Tab") {
            const focusable = [...el("board-editor-dock").querySelectorAll("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])")]
                .filter((item) => !item.hidden && item.getClientRects().length);
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
            }
        }
    });
    document.querySelectorAll(".copy-prompt-btn").forEach((button) => button.addEventListener("click", copyPrompt));

    el("bank-topic").addEventListener("change", () => {
        const input = el("bank-topic-new");
        const isNew = el("bank-topic").value === NEW_TOPIC;
        input.hidden = !isNew;
        input.required = isNew;
        if (isNew) input.focus();
    });

    el("board-topic").addEventListener("change", () => loadQuestionBoard());
    el("board-editor-dock").addEventListener("click", (event) => {
        if (event.target === el("board-editor-dock") && window.matchMedia("(max-width: 680px)").matches) cancelBoardEditor();
    });
    el("board-new-question").addEventListener("click", openNewBoardEditor);
    document.querySelectorAll(".board-column-add").forEach((button) => {
        button.addEventListener("click", () => {
            const columnState = button.closest(".question-board-column")?.dataset.boardState || "active";
            openNewBoardEditor(columnState === "reported" ? "active" : columnState);
        });
    });
    el("board-import-open").addEventListener("click", () => {
        if (state.boardEditor) { showError("Save or return the current question before importing."); return; }
        el("board-import-dialog").showModal();
    });
    el("board-import-cancel").addEventListener("click", () => el("board-import-dialog").close());
    el("import-file").addEventListener("change", async () => {
        const file = el("import-file").files?.[0];
        if (!file) return;
        try { el("import-content").value = await file.text(); }
        catch (err) { showError("Could not read that CSV file: " + err.message); }
    });
    el("board-rename-topic-btn").addEventListener("click", () => {
        const topic = el("board-rename-topic").value;
        if (!topic) { showError("Choose a topic to rename."); return; }
        const count = state.boardQuestions.filter((question) =>
            question.topic.toLowerCase() === topic.toLowerCase()
        ).length;
        renameTopic(topic, count);
    });
    document.querySelectorAll(".question-board-column").forEach((column) => {
        column.addEventListener("dragover", (event) => {
            if (!state.boardDragged) return;
            event.preventDefault();
            column.classList.add("is-over");
        });
        column.addEventListener("dragleave", (event) => {
            if (!column.contains(event.relatedTarget)) column.classList.remove("is-over");
        });
        column.addEventListener("drop", async (event) => {
            if (!state.boardDragged) return;
            event.preventDefault();
            column.classList.remove("is-over");
            if (column.dataset.boardAction === "delete") {
                if (state.boardEditor?.isNew && state.boardDragged.card === state.boardEditor.card) {
                    if (await confirmAction({
                        title: "Discard this unsaved question?",
                        message: "The new question has not been saved.",
                        confirmLabel: "Discard",
                    })) closeBoardEditor();
                    return;
                }
                deleteQuestion(state.boardDragged.questionId);
                return;
            }
            const targetState = column.dataset.boardState;
            if (targetState === "reported") {
                if (state.boardEditor && state.boardEditor.originalState === "reported" &&
                        state.boardDragged.card === state.boardEditor.card) {
                    saveBoardEditorAndMove(targetState, { fromDrop: true });
                    return;
                }
                showError("Questions enter Reported only when someone submits a report.");
                return;
            }
            if (state.boardEditor && state.boardDragged.card === state.boardEditor.card) {
                saveBoardEditorAndMove(targetState, { fromDrop: true });
            } else {
                moveBoardQuestion(state.boardDragged.questionId, targetState);
            }
        });
    });

    el("board-editor-dock").addEventListener("dragover", (event) => {
        if (state.boardDragged && (!state.boardEditor || state.boardDragged.card !== state.boardEditor.card)) {
            event.preventDefault();
            el("board-editor-drop").classList.add("is-over");
        }
    });
    el("board-editor-dock").addEventListener("dragleave", (event) => {
        if (!el("board-editor-dock").contains(event.relatedTarget)) el("board-editor-drop").classList.remove("is-over");
    });
    el("board-editor-dock").addEventListener("drop", (event) => {
        if (!state.boardDragged || (state.boardEditor && state.boardDragged.card === state.boardEditor.card)) return;
        event.preventDefault();
        el("board-editor-drop").classList.remove("is-over");
        openBoardEditor(state.boardDragged.question, state.boardDragged.card);
    });

    el("checks-prompt-btn").addEventListener("click", makeChecksPrompt);
    el("checks-import-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const content = el("checks-content").value.trim();
        if (!content) { showError("Paste the combined review CSV first."); return; }
        try {
            const payload = await api("/api/admin/question-check-review", { method: "POST", body: { content } });
            applyIdentity(payload);
            el("checks-content").value = "";
            showOk(payload.staged + " suggestion(s) sent for approval, " + payload.marked + " future-update flag(s) applied, " + payload.sent_to_human + " sent for human review, and " + (payload.report_count || 0) + " report(s) remain open.");
            loadChecks();
            loadAiReview();
            loadHumanReview();
            loadBank();
        } catch (err) { showError(err.message); }
    });
    el("reset-progress-btn").addEventListener("click", resetProgress);

    el("add-question-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        clearBanners();
        const question = el("bank-question").value.trim();
        if (!question) return;
        const topic = resolveTopic("bank-topic", "bank-topic-new");
        if (!topic) {
            showError("Choose a topic for the question.");
            return;
        }
        try {
            const payload = await api("/api/questions", {
                method: "POST",
                body: {
                    question_text: question,
                    answer_text: el("bank-answer").value.trim(),
                    topic: topic,
                },
            });
            el("add-question-form").reset();
            renderTopicSelect(el("bank-topic"), state.topics, "Choose a topic...", true, true);
            showOk("Added to the bank.");
            if (payload.counts) applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
            loadBank();
        } catch (err) {
            showError(err.message);
        }
    });

    el("import-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        clearBanners();
        const content = el("import-content").value;
        if (!content.trim()) {
            showError("Paste or upload your questions first.");
            return;
        }
        try {
            const payload = await api("/api/admin/import", {
                method: "POST",
                body: { content: content, format: "csv" },
            });
            applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
            el("import-content").value = "";
            el("import-file").value = "";
            el("board-import-dialog").close();
            showOk(payload.message);
            await loadQuestionBoard();
        } catch (err) {
            showError(err.message);
        }
    });

    el("delete-all-questions-btn").addEventListener("click", async () => {
        clearBanners();
        const values = await askForValues({
            title: "Permanently delete the entire question bank?",
            hint: "This removes every question and its linked reports and answer records. This cannot be undone. Type DELETE ALL QUESTIONS exactly to continue.",
            fields: [{ id: "confirm", label: "Confirmation", placeholder: "DELETE ALL QUESTIONS", required: true }],
            submitLabel: "Delete everything",
        });
        if (!values) return;
        if (values.confirm !== "DELETE ALL QUESTIONS") {
            showError("Nothing was deleted. The confirmation text did not match.");
            return;
        }
        try {
            const payload = await api("/api/admin/questions/delete-all", {
                method: "POST",
                body: { confirm: values.confirm },
            });
            applyIdentity({ counts: payload.counts, stale_count: payload.stale_count, report_count: payload.report_count });
            showOk(payload.message);
            loadBank();
        } catch (err) {
            showError(err.message);
        }
    });

    el("user-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        clearBanners();
        try {
            await api("/api/admin/users", {
                method: "POST",
                body: {
                    username: el("user-username").value.trim(),
                    display_name: el("user-display").value.trim(),
                    password: el("user-password").value,
                    role: el("user-role").value,
                },
            });
            el("user-form").reset();
            showOk("Account created.");
            loadUsers();
        } catch (err) {
            showError(err.message);
        }
    });
}

registerView("stats", loadStats);
registerView("progress-trends", loadProgressTrends);
registerView("sessions", loadSessions);
registerView("practice-stats", loadPracticeStats);
registerView("practice-trends", loadPracticeTrends);
registerView("practice-results", loadPracticeResults);
registerView("review", loadPending);
registerView("checks", loadChecks);
registerView("human-review", loadHumanReview);
registerView("ai-review", loadAiReview);
registerView("bank", loadBank);
registerView("board", loadQuestionBoard);
registerView("users", loadUsers);
registerView("website-issues", loadWebsiteIssues);
