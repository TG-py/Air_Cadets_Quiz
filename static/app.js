"use strict";

const NEW_TOPIC = "__new__";

const state = {
    user: null,
    csrf: null,
    counts: { approved: 0, pending: 0, rejected: 0, total: 0 },
    topics: [],
    submitTopics: [],
    question: null,
    topic: "",
    asked: 0,
    correct: 0,
    incorrect: 0,
    skipped: 0,
    answered: false,
    showAnswer: false,
};

const el = (id) => document.getElementById(id);

function clearBanners() {
    el("global-error").hidden = true;
    el("global-ok").hidden = true;
}

function showError(message) {
    const banner = el("global-error");
    banner.textContent = message;
    banner.hidden = false;
    el("global-ok").hidden = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function showOk(message) {
    const banner = el("global-ok");
    banner.textContent = message;
    banner.hidden = false;
    el("global-error").hidden = true;
}

async function api(path, options = {}) {
    const init = {
        method: options.method || "GET",
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
}

function setMenuOpen(open) {
    el("side-menu").classList.toggle("open", open);
    el("menu-overlay").hidden = !open;
    el("menu-toggle").setAttribute("aria-expanded", open ? "true" : "false");
    // the toggle shows only a symbol, so the accessible name must say it
    el("menu-toggle").setAttribute("aria-label", open ? "Close menu" : "Open menu");
    if (open) {
        el("menu-close").focus();
    }
}

function isMenuOpen() {
    return el("side-menu").classList.contains("open");
}

function setView(name) {
    state.view = name;
    setMenuOpen(false);
    document.querySelectorAll(".view").forEach((section) => {
        section.hidden = section.id !== "view-" + name;
    });
    document.querySelectorAll(".nav-btn").forEach((button) => {
        button.classList.toggle("active", button.dataset.view === name);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (name === "quiz") ensureQuestion();
    if (name === "stats") loadStats();
    if (name === "sessions") loadSessions();
    if (name === "submit") loadSubmitTopics();
    if (name === "review") loadPending();
    if (name === "bank") loadBank();
    if (name === "users") loadUsers();
}

function applyIdentity(payload) {
    if (payload.csrf) state.csrf = payload.csrf;
    if (payload.counts) state.counts = payload.counts;
    if (payload.topics) {
        state.topics = payload.topics;
        renderTopicSelect(el("quiz-topic"), state.topics, "All topics", "");
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
    document.querySelectorAll(".admin-only").forEach((button) => {
        button.hidden = !isAdmin;
    });
    document.querySelectorAll(".hide-for-admin").forEach((node) => {
        node.hidden = isAdmin;
    });
    if (isAdmin && state.view === "submit") setView("bank");

    if (signedIn) {
        const name = state.user.display_name || state.user.username;
        el("who").textContent =
            name + " (" + (isAdmin ? "admin" : "NCO") + ")";
    }

    const badge = el("review-badge");
    const pending = state.counts.pending || 0;
    badge.textContent = String(pending);
    badge.hidden = pending === 0;
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

    el("question-text").textContent = question.question_text;
    el("question-topic").textContent = question.topic;
    el("question-topic").hidden = !question.topic;
    el("answer-text").textContent = question.answer_text || "(no answer recorded)";
    el("answer-block").hidden = !state.showAnswer;
    el("reveal-btn").textContent = state.showAnswer ? "Hide answer" : "Show answer";

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
        actions.appendChild(makeButton("Edit", "", () => editQuestion(question)));
        actions.appendChild(
            makeButton("Delete", "no", () => deleteQuestion(question.id))
        );
    };
}

async function loadPending() {
    const list = el("review-list");
    try {
        const payload = await api("/api/admin/pending");
        applyIdentity({ counts: payload.counts });
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
                        actions.appendChild(
                            makeButton("Delete", "no", () => deleteQuestion(question.id))
                        );
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
        applyIdentity({ counts: payload.counts });
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
    } catch (err) {
        showError(err.message);
    }
}

async function deleteQuestion(questionId) {
    if (!window.confirm(
        "Delete this question permanently? Its recorded attempts and quiz-history entries will also be removed."
    )) return;
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/delete", {
            method: "POST",
            body: {},
        });
        applyIdentity({ counts: payload.counts });
        showOk("Question deleted.");
        loadPending();
        loadBank();
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

async function loadBank() {
    const list = el("bank-list");
    const search = el("bank-search").value.trim();
    const params = new URLSearchParams();
    params.set("include_archived", "1");
    if (search) params.set("q", search);
    try {
        const payload = await api("/api/questions?" + params.toString());
        applyIdentity({ counts: payload.counts, topics: payload.topics });
        list.replaceChildren();
        if (!payload.questions.length) {
            const empty = document.createElement("p");
            empty.className = "muted";
            empty.textContent = search
                ? "No questions match that search."
                : "No questions yet.";
            list.appendChild(empty);
            return;
        }
        BANK_GROUPS.forEach((group) => {
            list.appendChild(
                bankStatusGroup(
                    group,
                    payload.questions.filter((q) =>
                        group.value === "archived"
                            ? Boolean(q.archived_at)
                            : !q.archived_at && q.status === group.value
                    )
                )
            );
        });
    } catch (err) {
        showError(err.message);
    }
}

async function reviewFromBank(questionId, status) {
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/" + status, {
            method: "POST",
            body: {},
        });
        applyIdentity({ counts: payload.counts });
        showOk("Updated.");
        loadBank();
    } catch (err) {
        showError(err.message);
    }
}

async function archiveQuestion(questionId) {
    if (!window.confirm("Archive this question? It will leave the quiz, but its history will be kept.")) {
        return;
    }
    try {
        const payload = await api("/api/admin/questions/" + questionId + "/archive", {
            method: "POST",
            body: {},
        });
        applyIdentity({ counts: payload.counts });
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
        applyIdentity({ counts: payload.counts });
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
    const first = window.confirm(
        "Delete all progress for the whole squadron?\n\n" +
            "Every recorded correct, incorrect and skipped answer will be removed. " +
            "Questions, staff/NCO accounts and the question bank are kept."
    );
    if (!first) return;
    const second = window.confirm(
        "This cannot be undone.\n\nClick OK to permanently delete all recorded progress."
    );
    if (!second) return;
    try {
        await api("/api/admin/reset-progress", { method: "POST", body: { confirm: true } });
        showOk("All progress has been deleted.");
        loadStats();
    } catch (err) {
        showError(err.message);
    }
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

async function loadStats() {
    const overallBox = el("overall-stats");
    const topicBox = el("stats-topics");
    try {
        const payload = await api("/api/stats");

        overallBox.replaceChildren();
        [
            [payload.overall.asked, "questions asked"],
            [payload.overall.correct, "correct"],
            [payload.overall.incorrect, "incorrect"],
            [payload.overall.skipped, "skipped"],
            [accuracyLabel(payload.overall.accuracy), "squadron accuracy"],
        ].forEach(([value, label]) => overallBox.appendChild(statTile(value, label)));

        const byTopic = new Map();
        payload.questions.forEach((question) => {
            if (!byTopic.has(question.topic)) byTopic.set(question.topic, []);
            byTopic.get(question.topic).push(question);
        });

        topicBox.replaceChildren();
        el("stats-empty").hidden = payload.topics.length > 0;

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
    const first = window.confirm(
        "Delete this quiz session?\n\n" +
            "Every recorded correct, incorrect and skipped answer in this session will be removed. " +
            "Questions, staff/NCO accounts and the question bank are kept."
    );
    if (!first) return;
    const second = window.confirm(
        "This cannot be undone.\n\nClick OK to permanently delete this quiz session."
    );
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
    el("menu-toggle").addEventListener("click", () => setMenuOpen(!isMenuOpen()));
    el("menu-close").addEventListener("click", () => setMenuOpen(false));
    el("menu-overlay").addEventListener("click", () => setMenuOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && isMenuOpen()) {
            setMenuOpen(false);
            el("menu-toggle").focus();
        }
    });

    document.querySelectorAll(".nav-btn").forEach((button) => {
        button.addEventListener("click", () => setView(button.dataset.view));
    });

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
            if (state.user.must_change) {
                setView("password");
            } else {
                resetSessionCounters();
                setView("quiz");
            }
        } catch (err) {
            showError(err.message);
        }
    });

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

    el("quiz-topic").addEventListener("change", async () => {
        state.topic = el("quiz-topic").value;
        state.question = null;
        await loadNextQuestion();
    });

    el("correct-btn").addEventListener("click", () => recordAnswer(true, false));
    el("incorrect-btn").addEventListener("click", () => recordAnswer(false, false));
    el("skip-btn").addEventListener("click", () => recordAnswer(false, true));
    el("finish-btn").addEventListener("click", finishQuizSession);
    el("quiz-empty-finish").addEventListener("click", finishQuizSession);
    window.addEventListener("pagehide", finishOnPageHide);

    el("reveal-btn").addEventListener("click", () => {
        state.showAnswer = !state.showAnswer;
        localStorage.setItem("quiz.showAnswer", state.showAnswer ? "1" : "0");
        el("answer-block").hidden = !state.showAnswer;
        el("reveal-btn").textContent = state.showAnswer ? "Hide answer" : "Show answer";
    });

    el("summary-restart").addEventListener("click", () => {
        resetSessionCounters();
        loadNextQuestion();
    });

    el("bank-search").addEventListener("input", () => loadBank());
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
            if (payload.counts) applyIdentity({ counts: payload.counts });
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
                body: { content: content, format: el("import-format").value },
            });
            applyIdentity({ counts: payload.counts });
            el("import-content").value = "";
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
    state.showAnswer = localStorage.getItem("quiz.showAnswer") === "1";
    el("reveal-btn").textContent = state.showAnswer ? "Hide answer" : "Show answer";
    try {
        const payload = await api("/api/auth/me");
        applyIdentity(payload);
        await loadSubmitTopics();
        if (state.user) {
            if (state.user.must_change) setView("password");
            else {
                resetSessionCounters();
                setView("quiz");
            }
        } else {
            setView("submit");
        }
    } catch (err) {
        showError("Could not reach the server: " + err.message);
    }
}

document.addEventListener("DOMContentLoaded", boot);
