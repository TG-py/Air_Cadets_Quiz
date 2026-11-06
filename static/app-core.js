"use strict";
const viewLoaders = Object.create(null);
function registerView(name, loader) { viewLoaders[name] = loader; }
const NEW_TOPIC = "__new__";

const state = {
    user: null,
    csrf: null,
    counts: { approved: 0, pending: 0, rejected: 0, total: 0 },
    staleCount: 0,
    needsReviewCount: 0,
    aiPendingCount: 0,
    reportCount: 0,
    topics: [],
    boardQuestions: [],
    boardEditor: null,
    issueOriginView: "",
    submitTopics: [],
    question: null,
    topic: "",
    asked: 0,
    correct: 0,
    incorrect: 0,
    skipped: 0,
    answered: false,
    practice: {
        sessionId: null,
        name: "",
        topic: "",
        question: null,
        answered: false,
        showAnswer: false,
        asked: 0,
        correct: 0,
        incorrect: 0,
        skipped: 0,
    },
    pendingSubmit: null,
};

const el = (id) => document.getElementById(id);

function updateBoardMessageLayout() {
    const header = document.querySelector(".site-header");
    const hasMessage = !el("global-error").hidden || !el("global-ok").hidden;
    header.classList.toggle("has-message", hasMessage);
    document.body.style.setProperty("--mobile-header-height", Math.ceil(header.getBoundingClientRect().height) + "px");
    if (!document.body.classList.contains("board-view-active")) {
        document.body.style.removeProperty("--board-content-top");
        return;
    }
    requestAnimationFrame(() => {
        document.body.style.setProperty("--board-content-top", Math.ceil(header.getBoundingClientRect().bottom) + "px");
    });
}

function clearBanners() {
    el("global-error").hidden = true;
    el("global-ok").hidden = true;
    updateBoardMessageLayout();
}

function showError(message) {
    const banner = el("global-error");
    banner.textContent = message;
    banner.hidden = false;
    el("global-ok").hidden = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
    updateBoardMessageLayout();
}

function showOk(message) {
    const banner = el("global-ok");
    banner.textContent = message;
    banner.hidden = false;
    el("global-error").hidden = true;
    updateBoardMessageLayout();
}

async function api(path, options = {}) {
    const method = options.method || "GET";
    const submit = state.pendingSubmit;
    if (submit) {
        submit.claimed = true;
        state.pendingSubmit = null;
    }
    const focused = document.activeElement;
    const busyButton = submit?.button || (focused instanceof HTMLButtonElement ? focused : null);
    const busyForm = submit?.form || busyButton?.closest("form") || null;
    const busyControls = busyForm
        ? [...busyForm.querySelectorAll('button[type="submit"], input[type="submit"]')]
        : (busyButton ? [busyButton] : []);
    const priorDisabled = busyControls.map((control) => control.disabled);
    const restoreButtonFocus = busyButton === focused;
    busyControls.forEach((control) => { control.disabled = true; });
    if (busyButton) busyButton.setAttribute("aria-busy", "true");
    if (busyForm) busyForm.setAttribute("aria-busy", "true");
    const init = {
        method,
        headers: { Accept: "application/json" },
        credentials: "same-origin",
    };
    if (state.csrf && init.method !== "GET") {
        init.headers["X-CSRF-Token"] = state.csrf;
    }
    if (options.body) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(options.body);
    }
    try {
        const response = await fetch(path, init);
        let payload = {};
        try {
            payload = await response.json();
        } catch (err) {
            payload = {};
        }
        if (!response.ok) {
            const error = new Error(payload.error || "request failed");
            error.status = response.status;
            error.reason = payload.reason || "";
            throw error;
        }
        return payload;
    } finally {
        busyControls.forEach((control, index) => { control.disabled = priorDisabled[index]; });
        if (busyButton) {
            busyButton.removeAttribute("aria-busy");
            if (restoreButtonFocus && busyButton.isConnected) busyButton.focus({ preventScroll: true });
        }
        if (busyForm) busyForm.removeAttribute("aria-busy");
    }
}

function setMenuOpen(open) {
    el("side-menu").classList.toggle("open", open);
    el("menu-overlay").hidden = !open;
    el("menu-toggle").setAttribute("aria-expanded", open ? "true" : "false");
    // the toggle shows only a symbol, so the accessible name must say it
    el("menu-toggle").setAttribute("aria-label", open ? "Close menu" : "Open menu");
    if (!open) closeDotsMenus();
}

function isMenuOpen() {
    return el("side-menu").classList.contains("open");
}

function setView(name, { markNav = true } = {}) {
    if (state.boardEditor) {
        showError("Drop the expanded card into a board column to save before changing views.");
        return;
    }
    const leavingPractice = state.view === "practice" && name !== "practice";
    clearBanners();
    closeDotsMenus();
    document.querySelectorAll("dialog[open]").forEach((dialog) => {
        if (typeof dialog.closePrompt === "function") dialog.closePrompt(null);
        else dialog.close();
    });
    state.view = name;
    document.body.classList.toggle("board-view-active", name === "board");
    updateBoardMessageLayout();
    setMenuOpen(false);
    document.querySelectorAll(".view").forEach((section) => {
        section.hidden = section.id !== "view-" + name;
    });
    document.querySelectorAll(".nav-btn").forEach((button) => {
        button.classList.toggle("active", markNav && button.dataset.view === name);
    });
    document.querySelectorAll(".nav-group").forEach((group) => {
        if (group.querySelector('[data-view="' + name + '"]')) group.open = true;
    });
    const reviewToggle = el("question-review-toggle");
    if (reviewToggle) {
        reviewToggle.classList.toggle("active", ["board", "checks", "human-review", "ai-review"].includes(name));
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (leavingPractice) {
        closePracticeRun().then((payload) => {
            if (payload && state.view === "practice-results") loadPracticeResults();
        }).catch(() => {});
    }
    if (name === "practice") showPractice();
    if (name === "submit") loadSubmitTopics();
    const loader = viewLoaders[name];
    if (loader) loader();
}

function applyIdentity(payload) {
    if (payload.csrf) state.csrf = payload.csrf;
    if (payload.counts) state.counts = payload.counts;
    if (payload.topics) {
        state.topics = payload.topics;
        renderTopicSelect(el("quiz-topic"), state.topics, "All topics", "");
        renderTopicSelect(el("practice-topic"), state.topics, "All topics", "");
        renderTopicSelect(el("board-topic"), state.topics, "All topics", "");
        renderTopicSelect(el("board-rename-topic"), state.topics, "Choose a topic", "");
    }
    if (payload.user !== undefined) state.user = payload.user;

    const signedIn = Boolean(state.user);
    const isAdmin = signedIn && state.user.role === "admin";

    el("main-nav").hidden = false;
    el("who").hidden = !signedIn;
    el("login-link").hidden = signedIn;
    el("change-password-btn").hidden = !signedIn;
    el("logout-btn").hidden = !signedIn;

    document.querySelectorAll(".staff-only").forEach((button) => {
        button.hidden = !signedIn;
    });
    document.querySelectorAll(".admin-only:not(.view)").forEach((button) => {
        button.hidden = !isAdmin;
    });
    document.querySelectorAll(".hide-for-admin").forEach((node) => {
        node.hidden = isAdmin;
    });
    if (isAdmin && state.view === "submit") setView("board");

    if (signedIn) {
        const name = state.user.display_name || state.user.username;
        el("who").textContent =
            name + " (" + (isAdmin ? "admin" : "NCO") + ")";
    }

    const badge = el("review-badge");
    const pending = state.counts.pending || 0;
    if (badge) {
        badge.textContent = String(pending);
        badge.hidden = pending === 0;
    }

    const staleBadge = el("stale-badge");
    if (payload.stale_count !== undefined) state.staleCount = payload.stale_count;
    if (payload.needs_review_count !== undefined) state.needsReviewCount = payload.needs_review_count;
    if (staleBadge) {
        const staleCount =
            payload.stale_count !== undefined ? payload.stale_count : state.staleCount || 0;
        state.staleCount = staleCount;
        if (payload.needs_review_count !== undefined) state.needsReviewCount = payload.needs_review_count;
        staleBadge.textContent = String(staleCount);
        staleBadge.hidden = staleCount === 0;
    }
    const humanReviewBadge = el("human-review-badge");
    if (humanReviewBadge) {
        const count = payload.needs_review_count !== undefined ? payload.needs_review_count : state.needsReviewCount || 0;
        humanReviewBadge.textContent = String(count);
        humanReviewBadge.hidden = count === 0;
    }
    const aiReviewBadge = el("ai-review-badge");
    if (aiReviewBadge) {
        const count = payload.ai_pending_count !== undefined ? payload.ai_pending_count : state.aiPendingCount || 0;
        state.aiPendingCount = count;
        aiReviewBadge.textContent = String(count);
        aiReviewBadge.hidden = count === 0;
    }
    const reportBadge = el("report-badge");
    if (payload.report_count !== undefined) state.reportCount = payload.report_count;
    if (reportBadge) {
        const reportCount =
            payload.report_count !== undefined ? payload.report_count : state.reportCount || 0;
        state.reportCount = reportCount;
        reportBadge.textContent = String(reportCount);
        reportBadge.hidden = reportCount === 0;
    }
    const checkBadge = el("check-badge");
    if (checkBadge) {
        const checkCount = (state.staleCount || 0) + (state.reportCount || 0);
        checkBadge.textContent = String(checkCount);
        checkBadge.hidden = checkCount === 0;
    }
    if (isAdmin && payload.stale_count === undefined && payload.report_count === undefined &&
            typeof refreshAdminBadges === "function") {
        refreshAdminBadges();
    }
}

function renderTopicSelect(select, topics, firstLabel, allowNew, requireChoice) {
    if (!select) return;
    const current = select.value;
    select.replaceChildren();

    const first = document.createElement("option");
    first.value = "";
    first.textContent = firstLabel;
    // when a real topic is compulsory the prompt cannot be chosen, so the admin
    // cannot leave a question filed under a placeholder topic
    if (requireChoice) first.disabled = true;
    select.appendChild(first);

    topics.forEach((topic) => {
        const option = document.createElement("option");
        option.value = topic;
        option.textContent = topic;
        select.appendChild(option);
    });

    if (allowNew) {
        const option = document.createElement("option");
        option.value = NEW_TOPIC;
        option.textContent = "+ Add a new topic...";
        select.appendChild(option);
    }

    select.value = topics.includes(current) ? current : "";
    if (requireChoice && !select.value) first.selected = true;
    return select;
}

function renderSubmitTopicSelect() {
    const select = el("submit-topic");
    renderTopicSelect(select, state.submitTopics, "Choose a topic", true);
    syncNewTopicInput();
}

function syncNewTopicInput() {
    const select = el("submit-topic");
    const input = el("submit-topic-new");
    const isNew = select.value === NEW_TOPIC;
    input.hidden = !isNew;
    input.required = isNew;
    if (isNew) input.focus();
}

function resolveTopic(selectId, inputId) {
    const select = el(selectId);
    if (select.value === NEW_TOPIC) {
        return el(inputId).value.trim();
    }
    return select.value;
}

async function loadSubmitTopics() {
    try {
        const payload = await api("/api/topics");
        state.submitTopics = payload.topics || [];
        renderSubmitTopicSelect();
        if (el("bank-topic")) {
            renderTopicSelect(el("bank-topic"), state.topics, "Choose a topic...", true, true);
        }
    } catch (err) {
        showError(err.message);
    }
}

// ---- Solo practice: same bank, separate scoreboard, open to everyone ----

function resetPracticeCounters() {
    state.practice.asked = 0;
    state.practice.correct = 0;
    state.practice.incorrect = 0;
    state.practice.skipped = 0;
}

function updatePracticeProgress() {
    const parts = [state.practice.asked + " asked"];
    if (state.practice.correct) parts.push(state.practice.correct + " right");
    if (state.practice.incorrect) parts.push(state.practice.incorrect + " wrong");
    if (state.practice.skipped) parts.push(state.practice.skipped + " skipped");
    el("practice-progress").textContent = parts.join(" · ");
}

function updatePracticeAnswerControls() {
    const revealed = state.practice.showAnswer;
    el("practice-answer-block").hidden = !revealed;
    el("practice-reveal-btn").hidden = revealed;
    el("practice-skip-btn").hidden = revealed;
    el("practice-correct-btn").hidden = !revealed;
    el("practice-incorrect-btn").hidden = !revealed;
    el("practice-finish-btn").hidden = false;
}

function showPracticeStart() {
    el("practice-start").hidden = false;
    el("practice-panel").hidden = true;
    el("practice-empty").hidden = true;
    el("practice-summary").hidden = true;
}

function showPractice() {
    clearBanners();
    if (state.practice.sessionId) {
        loadPracticeNext();
    } else {
        showPracticeStart();
    }
}

function renderPracticeQuestion(question) {
    state.practice.question = question;
    state.practice.answered = false;
    state.practice.showAnswer = false;
    setPracticeMenuOpen(false);

    el("practice-question-text").textContent = question.question_text;
    el("practice-topic-tag").textContent = question.topic;
    el("practice-topic-tag").hidden = !question.topic;
    el("practice-answer-text").textContent = question.answer_text || "(no answer recorded)";
    el("practice-who").textContent = "Practising as " + state.practice.name;

    ["practice-correct-btn", "practice-incorrect-btn", "practice-skip-btn"].forEach((id) => {
        el(id).disabled = false;
    });
    updatePracticeAnswerControls();
    updatePracticeProgress();
}

async function loadPracticeNext() {
    clearBanners();
    el("practice-start").hidden = true;
    el("practice-summary").hidden = true;
    const params = new URLSearchParams();
    params.set("practice_session_id", String(state.practice.sessionId));
    try {
        const payload = await api("/api/practice/next?" + params.toString());
        el("practice-empty").hidden = true;
        el("practice-panel").hidden = false;
        renderPracticeQuestion(payload.question);
    } catch (err) {
        if (err.status === 409) {
            el("practice-panel").hidden = true;
            const exhausted = err.reason === "exhausted";
            el("practice-empty-title").textContent =
                exhausted ? "You have practised every question" : "No questions to practise yet";
            el("practice-empty-text").textContent = err.message;
            el("practice-empty").hidden = false;
            el("practice-empty-finish").hidden = !(
                exhausted || state.practice.asked > 0 || state.practice.skipped > 0
            );
            return;
        }
        if (err.status === 400) {
            state.practice.sessionId = null;
            showPracticeStart();
        }
        showError(err.message);
    }
}

async function recordPracticeAnswer(correct, skipped) {
    if (!state.practice.question || state.practice.answered) return;
    const questionId = state.practice.question.id;
    state.practice.answered = true;
    ["practice-correct-btn", "practice-incorrect-btn", "practice-skip-btn"].forEach((id) => {
        el(id).disabled = true;
    });

    if (!skipped) {
        state.practice.asked += 1;
        if (correct) state.practice.correct += 1;
        else state.practice.incorrect += 1;
    } else {
        state.practice.skipped += 1;
    }
    updatePracticeProgress();

    try {
        await api("/api/practice/attempts", {
            method: "POST",
            body: {
                practice_session_id: state.practice.sessionId,
                question_id: questionId,
                correct: correct,
                skipped: skipped,
            },
        });
    } catch (err) {
        showError("Could not save that answer: " + err.message);
        ["practice-correct-btn", "practice-incorrect-btn", "practice-skip-btn"].forEach((id) => {
            el(id).disabled = false;
        });
        state.practice.answered = false;
        return;
    }

    loadPracticeNext();
}

function closePracticeRun({ restoreOnError = false } = {}) {
    const sessionId = state.practice.sessionId;
    if (!sessionId) return Promise.resolve(null);
    state.practice.sessionId = null;
    return api("/api/practice/finish", {
        method: "POST",
        body: { practice_session_id: sessionId },
    }).catch((err) => {
        if (restoreOnError) state.practice.sessionId = sessionId;
        throw err;
    });
}

function closePracticeRunOnPageHide() {
    const sessionId = state.practice.sessionId;
    if (!sessionId) return;
    state.practice.sessionId = null;
    fetch("/api/practice/finish", {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": state.csrf || "",
        },
        body: JSON.stringify({ practice_session_id: sessionId }),
    }).catch(() => {});
}

async function finishPractice() {
    clearBanners();
    try {
        const payload = await closePracticeRun({ restoreOnError: true });
        if (!payload) return;
        if (!payload.finished || !payload.session) {
            resetPracticeCounters();
            showPracticeStart();
            return;
        }
        showPracticeSummary(payload.session);
    } catch (err) {
        showError(err.message);
    }
}

function showPracticeSummary(session) {
    el("practice-panel").hidden = true;
    el("practice-empty").hidden = true;
    el("practice-start").hidden = true;
    el("practice-summary").hidden = false;
    const scored = session.correct + session.incorrect;
    const accuracy = scored ? Math.round((session.correct / scored) * 100) : 0;
    el("practice-summary-text").textContent =
        state.practice.name + ": asked " + session.asked +
        ", right " + session.correct +
        ", wrong " + session.incorrect +
        ", skipped " + session.skipped +
        ". Accuracy " + accuracy + "% of " + scored + " answered question(s).";
    state.practice.question = null;
}

async function reportPracticeQuestion() {
    if (!state.practice.question) return;
    await sendQuestionReport(
        state.practice.question.id, "practice-menu", state.practice.name
    );
}

function practiceSummaryText(session) {
    const scored = session.correct + session.incorrect;
    const accuracy = scored ? Math.round((session.correct / scored) * 100) : 0;
    return (
        session.asked +
        " asked · " +
        session.correct +
        " right · " +
        session.incorrect +
        " wrong · " +
        session.skipped +
        " skipped · " +
        accuracy +
        "% accuracy"
    );
}

function setDotsMenuOpen(menuId, open) {
    el(menuId).hidden = !open;
    el(menuId + "-btn").setAttribute("aria-expanded", open ? "true" : "false");
}

function setPracticeMenuOpen(open) {
    setDotsMenuOpen("practice-menu", open);
}

function closeDotsMenus(restoreFocus = false) {
    ["question-menu", "practice-menu", "issue-menu"].forEach((id) => {
        if (el(id) && !el(id).hidden) {
            setDotsMenuOpen(id, false);
            if (restoreFocus) el(id + "-btn").focus();
        }
    });
}

async function sendQuestionReport(questionId, menuId, defaultName) {
    if (menuId) setDotsMenuOpen(menuId, false);
    const fields = [];
    // guests report under the name they give; signed-in staff report as themselves
    if (!state.user && defaultName !== null) {
        fields.push({
            id: "reporter_name",
            label: "Your name",
            value: defaultName || "",
            maxlength: 80,
        });
    }
    fields.push({
        id: "reason",
        label: "What is wrong? (optional)",
        value: "",
        rows: 3,
        maxlength: 1000,
        placeholder: "e.g. The answer should be ... because ...",
    });
    const values = await askForValues({
        title: "Report incorrect question",
        hint: "Say what is wrong if you can - the question, the answer, or both. An admin will check it.",
        fields: fields,
        submitLabel: "Send report",
    });
    if (values === null) return;
    const body = { reason: values.reason };
    if (!state.user && defaultName !== null) {
        body.reporter_name = values.reporter_name;
    }
    try {
        const payload = await api("/api/questions/" + questionId + "/report", {
            method: "POST",
            body: body,
        });
        showOk(payload.message || "Reported - an admin will check it.");
    } catch (err) {
        showError(err.message);
    }
}

function confirmAction(options) {
    return new Promise((resolve) => {
        const dialog = document.createElement("dialog");
        dialog.className = "modal";

        const form = document.createElement("form");
        form.className = "modal-form";

        const title = document.createElement("h3");
        title.textContent = options.title || "Are you sure?";
        form.appendChild(title);

        if (options.message) {
            const message = document.createElement("p");
            message.className = "hint";
            message.textContent = options.message;
            form.appendChild(message);
        }

        const row = document.createElement("div");
        row.className = "modal-actions";
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "ghost";
        cancel.textContent = options.cancelLabel || "Cancel";
        const confirm = document.createElement("button");
        confirm.type = "submit";
        confirm.className = options.danger === false ? "primary" : "no";
        confirm.textContent = options.confirmLabel || "Delete";
        row.appendChild(cancel);
        row.appendChild(confirm);
        form.appendChild(row);

        function close(result) {
            dialog.close();
            dialog.remove();
            resolve(result);
        }
        dialog.closePrompt = close;

        cancel.addEventListener("click", () => close(false));
        dialog.addEventListener("cancel", (event) => {
            event.preventDefault();
            close(false);
        });
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            close(true);
        });

        dialog.appendChild(form);
        document.body.appendChild(dialog);
        dialog.showModal();
        confirm.focus();
    });
}

// Replaces window.prompt: builds a real form in the page and resolves with the
// entered values, or null if the admin cancels or presses Escape.
function askForValues(options) {
    const fields = options.fields || [];
    return new Promise((resolve) => {
        const dialog = document.createElement("dialog");
        dialog.className = "modal";

        const form = document.createElement("form");
        form.className = "modal-form";

        const title = document.createElement("h3");
        title.textContent = options.title || "";
        form.appendChild(title);

        if (options.hint) {
            const hint = document.createElement("p");
            hint.className = "hint";
            hint.textContent = options.hint;
            form.appendChild(hint);
        }

        const inputs = {};
        fields.forEach((field) => {
            const label = document.createElement("label");
            label.setAttribute("for", "modal-" + field.id);
            label.textContent = field.label;
            form.appendChild(label);

            const input = document.createElement(field.rows ? "textarea" : "input");
            input.id = "modal-" + field.id;
            if (!field.rows) input.type = field.type || "text";
            if (field.rows) input.rows = field.rows;
            if (field.value) input.value = field.value;
            if (field.maxlength) input.maxLength = field.maxlength;
            if (field.minlength) input.minLength = field.minlength;
            if (field.placeholder) input.placeholder = field.placeholder;
            if (field.list) input.setAttribute("list", field.list);
            if (field.readonly) {
                input.readOnly = true;
                input.addEventListener("click", () => input.select());
            }
            form.appendChild(input);
            inputs[field.id] = input;
            if (field.readonly) {
                const note = document.createElement("p");
                note.className = "hint";
                note.textContent = field.note || "Click to select, then copy.";
                form.appendChild(note);
            }

            if (field.list) {
                const data = document.createElement("datalist");
                data.id = field.list;
                field.options.forEach((option) => {
                    const entry = document.createElement("option");
                    entry.value = option;
                    data.appendChild(entry);
                });
                form.appendChild(data);
            }

            if (field.type === "password" && !field.readonly) {
                const show = document.createElement("label");
                show.className = "checkbox";
                const box = document.createElement("input");
                box.type = "checkbox";
                box.addEventListener("change", () => {
                    input.type = box.checked ? "text" : "password";
                });
                show.appendChild(box);
                show.appendChild(document.createTextNode(" Show as you type"));
                form.appendChild(show);
            }
        });

        const row = document.createElement("div");
        row.className = "modal-actions";
        const cancel = document.createElement("button");
        cancel.type = "button";
        // ghost matches .primary box for box, so the pair lines up
        cancel.className = "ghost";
        cancel.textContent = "Cancel";
        const submit = document.createElement("button");
        submit.type = "submit";
        submit.className = "primary";
        submit.textContent = options.submitLabel || "Save";
        row.appendChild(cancel);
        row.appendChild(submit);
        form.appendChild(row);

        function close(result) {
            dialog.close();
            dialog.remove();
            resolve(result);
        }
        dialog.closePrompt = close;

        cancel.addEventListener("click", () => close(null));
        dialog.addEventListener("cancel", (event) => {
            event.preventDefault();
            close(null);
        });
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const values = {};
            fields.forEach((field) => {
                values[field.id] = inputs[field.id].value.trim();
            });
            close(values);
        });

        dialog.appendChild(form);
        document.body.appendChild(dialog);
        dialog.showModal();
        const first = fields.length ? inputs[fields[0].id] : null;
        if (first) {
            first.focus();
            if (first.select) first.select();
        }
    });
}

async function submitWebsiteIssue(event) {
    event.preventDefault();
    clearBanners();
    try {
        const payload = await api("/api/website-issues", {
            method: "POST",
            body: {
                title: el("website-issue-title").value.trim(),
                details: el("website-issue-details").value.trim(),
                page: state.issueOriginView || "unknown",
            },
        });
        el("website-issue-form").reset();
        showOk(payload.message || "Website issue reported.");
    } catch (err) {
        showError(err.message);
    }
}

function bindEvents() {
    document.addEventListener("submit", (event) => {
        const form = event.target;
        const button = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
        const pending = { form, button, claimed: false };
        state.pendingSubmit = pending;
        queueMicrotask(() => {
            if (!pending.claimed && state.pendingSubmit === pending) state.pendingSubmit = null;
        });
    }, true);
    window.addEventListener("resize", () => {
        updateBoardMessageLayout();
        const allowDrag = !window.matchMedia("(max-width: 680px)").matches;
        document.querySelectorAll(".board-question-card").forEach((card) => { card.draggable = allowDrag; });
    });
    el("menu-toggle").addEventListener("click", () => setMenuOpen(!isMenuOpen()));
    el("menu-overlay").addEventListener("click", () => setMenuOpen(false));
    el("issue-menu-btn").addEventListener("click", (event) => {
        event.stopPropagation();
        setDotsMenuOpen("issue-menu", el("issue-menu").hidden);
    });
    el("issue-report-btn").addEventListener("click", () => {
        setDotsMenuOpen("issue-menu", false);
        state.issueOriginView = state.view || "unknown";
        setView("report-issue");
    });
    el("website-issue-form").addEventListener("submit", submitWebsiteIssue);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && isMenuOpen()) {
            setMenuOpen(false);
            el("menu-toggle").focus();
        }
    });

    document.querySelectorAll(".nav-btn[data-view]").forEach((button) => {
        button.addEventListener("click", () => setView(button.dataset.view));
    });

    el("login-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        clearBanners();
        const username = el("login-username").value;
        const password = el("login-password").value;
        try {
            await api("/api/auth/login", {
                method: "POST",
                body: { username: username, password: password },
            });
            el("login-password").value = "";
            location.reload();
        } catch (err) {
            showError(err.message);
        }
    });

    window.addEventListener("pagehide", closePracticeRunOnPageHide);

    el("logout-btn").addEventListener("click", async () => {
        try {
            await api("/api/auth/logout", { method: "POST", body: {} });
        } catch (err) {
            showError(err.message);
        }
        location.reload();
    });

    el("change-password-btn").addEventListener("click", () => setView("password"));

    el("login-link").addEventListener("click", () => setView("login"));

    const passwordForm = el("password-form");
    if (passwordForm) {
        passwordForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            clearBanners();
            const current = el("current-password").value;
            const next = el("new-password").value;
            const confirm = el("confirm-password").value;
            if (next !== confirm) {
                showError("The two new passwords do not match.");
                return;
            }
            try {
                const payload = await api("/api/auth/change-password", {
                    method: "POST",
                    body: { current_password: current, new_password: next },
                });
                passwordForm.reset();
                showOk(payload.message || "Password changed.");
                setTimeout(() => location.reload(), 1200);
            } catch (err) {
                showError(err.message);
            }
        });
    }

    el("submit-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        clearBanners();

        const name = el("submit-name").value.trim();
        const question = el("submit-question").value.trim();
        const answer = el("submit-answer").value.trim();
        const topic = resolveTopic("submit-topic", "submit-topic-new");

        const missing = [];
        if (!name) missing.push("your name");
        if (!question) missing.push("a question");
        if (!answer) missing.push("an answer");
        if (!topic) missing.push("a topic");
        if (missing.length) {
            showError("Please fill in " + missing.join(", ") + ".");
            return;
        }

        try {
            const payload = await api("/api/questions", {
                method: "POST",
                body: {
                    question_text: question,
                    answer_text: answer,
                    topic: topic,
                    submitted_by: name,
                },
            });
            el("submit-form").reset();
            renderSubmitTopicSelect();
            showOk(payload.message);
        } catch (err) {
            showError(err.message);
        }
    });

    el("submit-topic").addEventListener("change", syncNewTopicInput);

    document.addEventListener("click", (event) => {
        if (event.target.closest && event.target.closest(".dots-wrap")) return;
        closeDotsMenus();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeDotsMenus(true);
        }
    });
    el("practice-menu-btn").addEventListener("click", (event) => {
        event.stopPropagation();
        setPracticeMenuOpen(el("practice-menu").hidden);
    });
    el("practice-report-btn").addEventListener("click", reportPracticeQuestion);

    el("practice-start-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        clearBanners();
        const name = el("practice-name").value.trim();
        if (name.length < 2) {
            showError("Please enter your name before practising.");
            return;
        }
        try {
            const payload = await api("/api/practice/start", {
                method: "POST",
                body: { name: name, topic: el("practice-topic").value },
            });
            state.practice.sessionId = payload.practice_session_id;
            state.practice.name = payload.name;
            state.practice.topic = payload.topic || "";
            state.practice.question = null;
            resetPracticeCounters();
            loadPracticeNext();
        } catch (err) {
            showError(err.message);
        }
    });

    el("practice-correct-btn").addEventListener("click", () => recordPracticeAnswer(true, false));
    el("practice-incorrect-btn").addEventListener("click", () => recordPracticeAnswer(false, false));
    el("practice-skip-btn").addEventListener("click", () => recordPracticeAnswer(false, true));
    el("practice-finish-btn").addEventListener("click", finishPractice);
    el("practice-empty-finish").addEventListener("click", finishPractice);

    el("practice-reveal-btn").addEventListener("click", () => {
        state.practice.showAnswer = true;
        updatePracticeAnswerControls();
    });

    el("practice-restart").addEventListener("click", async () => {
        try {
            const payload = await api("/api/practice/start", {
                method: "POST",
                body: { name: state.practice.name, topic: state.practice.topic },
            });
            state.practice.sessionId = payload.practice_session_id;
            state.practice.question = null;
            resetPracticeCounters();
            loadPracticeNext();
        } catch (err) {
            showError(err.message);
        }
    });

    el("practice-switch").addEventListener("click", async () => {
        if (state.practice.sessionId) {
            try {
                await api("/api/practice/finish", {
                    method: "POST",
                    body: { practice_session_id: state.practice.sessionId },
                });
            } catch (err) {
            }
        }
        state.practice.sessionId = null;
        state.practice.question = null;
        resetPracticeCounters();
        showPracticeStart();
    });

    if (typeof bindStaffEvents === "function") bindStaffEvents();
    if (typeof bindAdminEvents === "function") bindAdminEvents();
}

async function boot() {
    bindEvents();
    try {
        const payload = await api("/api/auth/me");
        applyIdentity(payload);
        await loadSubmitTopics();
        if (state.user) {
            if (state.user.role === "admin" && state.user.must_change) setView("password");
            else {
                resetSessionCounters();
                setView("quiz", { markNav: false });
            }
        } else {
            setView("practice");
        }
    } catch (err) {
        showError("Could not reach the server: " + err.message);
    }
}

document.addEventListener("DOMContentLoaded", boot);
