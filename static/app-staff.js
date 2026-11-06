"use strict";

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

function setQuestionMenuOpen(open) {
    setDotsMenuOpen("question-menu", open);
}

async function reportCurrentQuestion() {
    if (!state.question) return;
    setQuestionMenuOpen(false);
    el("question-menu-btn").focus();
    await sendQuestionReport(state.question.id, null);
}

function bindStaffEvents() {
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
    el("finish-btn").addEventListener("click", finishQuizSession);
    el("quiz-empty-finish").addEventListener("click", finishQuizSession);
    window.addEventListener("pagehide", finishOnPageHide);

    el("summary-restart").addEventListener("click", () => {
        resetSessionCounters();
        loadNextQuestion();
    });
}

registerView("quiz", ensureQuestion);
