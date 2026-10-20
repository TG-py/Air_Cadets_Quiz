"use strict";

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
    el("question-review-toggle").classList.toggle("active", ["board", "checks", "human-review", "ai-review"].includes(name));
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (leavingPractice) {
        closePracticeRun().then((payload) => {
            if (payload && state.view === "practice-results") loadPracticeResults();
        }).catch(() => {});
    }
    if (name === "quiz") ensureQuestion();
    if (name === "practice") showPractice();
    if (name === "practice-results") loadPracticeResults();
    if (name === "stats") loadStats();
    if (name === "practice-stats") loadPracticeStats();
    if (name === "progress-trends") loadProgressTrends();
    if (name === "practice-trends") loadPracticeTrends();
    if (name === "website-issues") loadWebsiteIssues();
    if (name === "sessions") loadSessions();
    if (name === "submit") loadSubmitTopics();
    if (name === "review") loadPending();
    if (name === "checks") loadChecks();
    if (name === "human-review") loadHumanReview();
    if (name === "ai-review") loadAiReview();
    if (name === "bank") loadBank();
    if (name === "board") loadQuestionBoard();
    if (name === "users") loadUsers();
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
    badge.textContent = String(pending);
    badge.hidden = pending === 0;

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
        renderTopicSelect(el("bank-topic"), state.topics, "Choose a topic...", true, true);
    } catch (err) {
        showError(err.message);
    }
}

function resetSessionCounters() {
    state.asked = 0;
    state.correct = 0;
    state.incorrect = 0;
    state.skipped = 0;
}

function updateProgress() {
    const parts = [state.asked + " asked"];
    if (state.correct) parts.push(state.correct + " correct");
    if (state.incorrect) parts.push(state.incorrect + " incorrect");
    if (state.skipped) parts.push(state.skipped + " skipped");
    el("quiz-progress").textContent = parts.join(" · ");
}

function renderQuestion(question) {
    state.question = question;
    state.answered = false;
    document.body.classList.remove("answered-correct", "answered-incorrect");
    setQuestionMenuOpen(false);

    el("question-text").textContent = question.question_text;
    el("question-topic").textContent = question.topic;
    el("question-topic").hidden = !question.topic;
    el("answer-text").textContent = question.answer_text || "(no answer recorded)";
    el("answer-block").hidden = false;

    ["correct-btn", "incorrect-btn", "skip-btn"].forEach((id) => {
        el(id).disabled = false;
    });
    updateProgress();
}

async function ensureQuestion() {
    if (state.question && !state.answered) return;
    await loadNextQuestion();
}

async function loadNextQuestion() {
    clearBanners();
    const params = new URLSearchParams();
    if (state.topic) params.set("topic", state.topic);
    el("quiz-summary").hidden = true;
    try {
        const payload = await api("/api/quiz/next?" + params.toString());
        el("quiz-empty").hidden = true;
        el("quiz-panel").hidden = false;
        renderQuestion(payload.question);
    } catch (err) {
        if (err.status === 409) {
            el("quiz-panel").hidden = true;
            const exhausted = err.reason === "exhausted";
            el("quiz-empty-title").textContent =
                exhausted ? "No more questions left to ask" : "No questions to ask yet";
            el("quiz-empty-text").textContent = err.message;
            el("quiz-empty").hidden = false;
            // keep a way out when the bank runs dry: finishing from here
            // closes the run so it lands straight on the sessions board,
            // and clears the asked list so asking again starts a fresh run.
            // (also shown after a dead-end topic switch mid-session.)
            el("quiz-empty-finish").hidden = !(
                exhausted || state.asked > 0 || state.skipped > 0
            );
            return;
        }
        showError(err.message);
    }
}

async function finishQuizSession() {
    clearBanners();
    try {
        await api("/api/quiz/finish", { method: "POST", body: {} });
    } catch (err) {
        showError(err.message);
        return;
    }
    // admins own the sessions board, so a finished run goes straight on it;
    // everyone else gets the usual summary with a way to start another run.
    if (state.user && state.user.role === "admin") {
        resetSessionCounters();
        state.question = null;
        setView("sessions");
        showOk("Session finished.");
        return;
    }
    showSummary();
}

// closing or reloading the tab exits the run too, so an abandoned session
// still lands on the sessions board instead of staying open forever.
function finishOnPageHide() {
    if (!state.user || !state.csrf) return;
    try {
        fetch("/api/quiz/finish", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": state.csrf,
            },
            body: "{}",
            credentials: "same-origin",
            keepalive: true,
        });
    } catch (err) {
        // nothing useful to show during unload
    }
}

function showSummary() {
    el("quiz-panel").hidden = true;
    el("quiz-empty").hidden = true;
    el("quiz-summary").hidden = false;
    const scored = state.correct + state.incorrect;
    const accuracy = scored ? Math.round((state.correct / scored) * 100) : 0;
    el("summary-text").textContent =
        "Asked " +
        state.asked +
        ", correct " +
        state.correct +
        ", incorrect " +
        state.incorrect +
        ", skipped " +
        state.skipped +
        ". Accuracy " +
        accuracy +
        "% of " +
        scored +
        " answered question(s). This is added to the squadron total.";
    state.question = null;
}

async function recordAnswer(correct, skipped) {
    if (!state.question || state.answered) return;
    const questionId = state.question.id;
    state.answered = true;
    ["correct-btn", "incorrect-btn", "skip-btn"].forEach((id) => {
        el(id).disabled = true;
    });

    document.body.classList.remove("answered-correct", "answered-incorrect");
    if (!skipped) {
        document.body.classList.add(correct ? "answered-correct" : "answered-incorrect");
        state.asked += 1;
        if (correct) state.correct += 1;
        else state.incorrect += 1;
    } else {
        state.skipped += 1;
    }
    updateProgress();

    try {
        await api("/api/attempts", {
            method: "POST",
            body: {
                question_id: questionId,
                correct: correct,
                skipped: skipped,
                topic_filter: state.topic || "",
            },
        });
    } catch (err) {
        if (err.status === 400 || err.status === 401) {
            showError("Could not save that answer: " + err.message);
            ["correct-btn", "incorrect-btn", "skip-btn"].forEach((id) => {
                el(id).disabled = false;
            });
            state.answered = false;
            return;
        }
        throw err;
    }

    loadNextQuestion();
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

function setDotsMenuOpen(menuId, open) {
    el(menuId).hidden = !open;
    el(menuId + "-btn").setAttribute("aria-expanded", open ? "true" : "false");
}

function setQuestionMenuOpen(open) {
    setDotsMenuOpen("question-menu", open);
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

async function reportCurrentQuestion() {
    if (!state.question) return;
    setQuestionMenuOpen(false);
    el("question-menu-btn").focus();
    await sendQuestionReport(state.question.id, null);
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
    topicSelect.value = question.topic || availableTopics[0] || "";
    topicSelect.required = true;
    fields.append(questionLabel, questionInput, answerLabel, answerInput, topicLabel, topicSelect);
    [questionInput, answerInput, topicSelect].forEach((control) => {
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
        el("board-edit-topic").value.trim() !== (editor.question.topic || "");
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
    } catch (err) { showError(err.message); }
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

async function saveBoardEditorAndMove(targetState) {
    const editor = state.boardEditor;
    if (!editor) return;
    const question = editor.question;
    const originalState = editor.originalState;
    const fields = {
        question_text: el("board-edit-question").value.trim(),
        answer_text: el("board-edit-answer").value.trim(),
        topic: el("board-edit-topic").value.trim(),
    };
    if (!fields.question_text || !fields.topic || (editor.isNew && !fields.answer_text)) {
        showError("A question and topic are required; new questions also need an answer.");
        return;
    }
    if (editor.isNew) {
        if (targetState === "reported") { showError("A new question cannot be moved to Reported without a user report."); return; }
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
            await loadQuestionBoard({ preserveEditor: true });
            closeBoardEditor({ restoreCard: false });
            showOk("New question added to " + (BOARD_COLUMNS.find((column) => column.id === targetState)?.label || "the board") + ".");
        } catch (err) { showError(err.message); }
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
    try {
        if (changed) await api("/api/admin/questions/" + question.id + "/edit", { method: "POST", body: fields });
        if (targetState !== "reported" && (targetState !== editor.originalState || changed || question.status === "pending" && targetState === "active")) {
            const payload = await api("/api/admin/questions/" + question.id + "/board-state", {
                method: "POST", body: { state: targetState },
            });
            applyIdentity(payload);
        }
        await loadQuestionBoard({ preserveEditor: true });
        closeBoardEditor({ restoreCard: false });
        const destination = BOARD_COLUMNS.find((column) => column.id === targetState)?.label || "its column";
        showOk(changed ? "Question details saved in " + destination + "." :
            targetState === originalState ? "Question returned to its previous column." : "Question moved to " + destination + ".");
    } catch (err) { showError(err.message); }
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
    window.addEventListener("beforeunload", (event) => {
        if (!state.boardEditor) return;
        event.preventDefault();
        event.returnValue = "";
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
        if (event.key === "Escape" && isMenuOpen()) {
            setMenuOpen(false);
            el("menu-toggle").focus();
        }
    });

    document.querySelectorAll(".nav-btn[data-view]").forEach((button) => {
        button.addEventListener("click", () => setView(button.dataset.view));
    });
    document.querySelectorAll(".copy-prompt-btn").forEach((button) => button.addEventListener("click", copyPrompt));

    el("login-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        clearBanners();
        const username = el("login-username").value;
        const password = el("login-password").value;
        try {
            const payload = await api("/api/auth/login", {
                method: "POST",
                body: { username: username, password: password },
            });
            el("login-password").value = "";
            applyIdentity(payload);
            if (state.user.role === "admin" && state.user.must_change) {
                setView("password");
            } else {
                resetSessionCounters();
                setView("quiz");
            }
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

    el("password-form").addEventListener("submit", async (event) => {
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
            el("password-form").reset();
            showOk(payload.message || "Password changed.");
            setTimeout(() => location.reload(), 1200);
        } catch (err) {
            showError(err.message);
        }
    });

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
                    saveBoardEditorAndMove(targetState);
                    return;
                }
                showError("Questions enter Reported only when someone submits a report.");
                return;
            }
            if (state.boardEditor && state.boardDragged.card === state.boardEditor.card) {
                saveBoardEditorAndMove(targetState);
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

    el("quiz-topic").addEventListener("change", async () => {
        state.topic = el("quiz-topic").value;
        state.question = null;
        await loadNextQuestion();
    });

    el("correct-btn").addEventListener("click", () => recordAnswer(true, false));
    el("incorrect-btn").addEventListener("click", () => recordAnswer(false, false));
    el("skip-btn").addEventListener("click", () => recordAnswer(false, true));
    el("question-menu-btn").addEventListener("click", (event) => {
        event.stopPropagation();
        setQuestionMenuOpen(el("question-menu").hidden);
    });
    el("report-question-btn").addEventListener("click", reportCurrentQuestion);
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
    el("finish-btn").addEventListener("click", finishQuizSession);
    el("quiz-empty-finish").addEventListener("click", finishQuizSession);
    window.addEventListener("pagehide", finishOnPageHide);

    el("summary-restart").addEventListener("click", () => {
        resetSessionCounters();
        loadNextQuestion();
    });

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
        // a fresh run under the same name; the old one is already finished
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
        // switching name ends this run first so the score keeps its name
        if (state.practice.sessionId) {
            try {
                await api("/api/practice/finish", {
                    method: "POST",
                    body: { practice_session_id: state.practice.sessionId },
                });
            } catch (err) {
                // an empty or unknown run simply drops away
            }
        }
        state.practice.sessionId = null;
        state.practice.question = null;
        resetPracticeCounters();
        showPracticeStart();
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
