import React, { useEffect, useMemo, useState } from "react";
import catchLogo from "./assets/catch.png";

const DO_COMPONENT_PATHS = {
  auth: "catch-auth-service",
  game: "catch-game-service",
  teacher: "catch-teacher-service",
  integration: "catch-integration",
};

function cleanUrl(url) {
  return url ? url.replace(/\/+$/, "") : "";
}

function serviceUrl(envUrl, localUrl, componentPath) {
  const configuredUrl = cleanUrl(envUrl);
  if (configuredUrl) return configuredUrl;

  const isLocalHost = ["localhost", "127.0.0.1"].includes(
    window.location.hostname,
  );
  if (isLocalHost) return localUrl;

  return `${window.location.origin}/${componentPath}`;
}

const GAME_URL = serviceUrl(
  import.meta.env.VITE_GAME_SERVICE_URL,
  "http://localhost:8000",
  DO_COMPONENT_PATHS.game,
);
const AUTH_URL = serviceUrl(
  import.meta.env.VITE_AUTH_SERVICE_URL,
  "http://localhost:8002",
  DO_COMPONENT_PATHS.auth,
);
const TEACHER_URL = serviceUrl(
  import.meta.env.VITE_TEACHER_SERVICE_URL,
  "http://localhost:8003",
  DO_COMPONENT_PATHS.teacher,
);
const INTEGRATION_URL = serviceUrl(
  import.meta.env.VITE_INTEGRATION_SERVICE_URL,
  "http://localhost:8004",
  DO_COMPONENT_PATHS.integration,
);

const kittenTabs = [
  ["quiz", "Quiz"],
  ["fishing", "Fish"],
  ["aquarium", "Aquarium"],
  ["market", "Market"],
  ["leaderboard", "Leaderboard"],
];

const catTabs = [["teacher", "Teacher"]];
const SESSION_VERSION = "2";
const defaultTeacherProblem = {
  title: "Return the larger number",
  prompt: "Write a function solve(a, b) that returns the larger number.",
  starter_code: "def solve(a, b):\n    pass\n",
  reference_solution: "def solve(a, b):\n    return max(a, b)\n",
  test_code:
    "assert solve(1, 2) == 2\nassert solve(7, 3) == 7\nassert solve(-1, -5) == -1\n",
  topic: "conditionals",
};

function emptyInventory(userId) {
  return {
    user_id: userId,
    fish: [],
    total_count: 0,
    tokens: 0,
    fishing_chances: 0,
  };
}

function loadStoredSession() {
  const version = localStorage.getItem("catch_session_version");
  const token = localStorage.getItem("catch_token");
  const userId = localStorage.getItem("catch_user_id");
  const role = localStorage.getItem("catch_role");
  const username = localStorage.getItem("catch_username");
  if (version !== SESSION_VERSION) return null;
  if (!token || !userId || !role) return null;
  return { token, user_id: userId, role, username: username || userId };
}

function formatApiError(data) {
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => {
        const field = item.loc?.[item.loc.length - 1];
        if (
          field === "username" &&
          item.type === "string_too_short"
        ) {
          return "Username must be at least 2 characters.";
        }
        if (
          field === "password" &&
          item.type === "string_too_short"
        ) {
          return "Password must be at least 8 characters.";
        }
        if (
          field === "new_password" &&
          item.type === "string_too_short"
        ) {
          return "New password must be at least 8 characters.";
        }
        if (field === "email" && item.type?.includes("value_error")) {
          return "Enter a valid email address.";
        }
        return item.msg || "Request failed";
      })
      .join(" ");
  }
  if (typeof data.detail === "string") return data.detail;
  if (data.message) return data.message;
  return "Request failed";
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(formatApiError(data));
  }
  return data;
}

function imageUrl(path) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${GAME_URL}${path}`;
}

function Status({ error, message }) {
  if (!error && !message) return null;
  return <p className={error ? "status error" : "status"}>{error || message}</p>;
}

function AuthPanel({ session, setSession }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("kitten");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function storeSession(data) {
    localStorage.setItem("catch_user_id", data.user_id);
    localStorage.setItem("catch_role", data.role);
    localStorage.setItem("catch_token", data.token);
    localStorage.setItem("catch_username", data.username);
    localStorage.setItem("catch_session_version", SESSION_VERSION);
    setSession(data);
  }

  function switchMode(nextMode) {
    setError("");
    setMessage("");
    setPassword("");
    setNewPassword("");
    setVerificationCode("");
    setMode(nextMode);
  }

  async function requestEmailCode() {
    setError("");
    setMessage("");
    setSubmitting(true);
    try {
      const data = await request(`${AUTH_URL}/auth/verification-code/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, role }),
      });
      setMessage(
        data.debug_code
          ? `Local demo code: ${data.debug_code}`
          : "Verification code sent. Check your email.",
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function submitAuth() {
    setError("");
    setMessage("");
    setSubmitting(true);
    try {
      if (mode === "email-code") {
        const data = await request(`${AUTH_URL}/auth/verification-code/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            code: verificationCode,
            role,
          }),
        });
        storeSession(data);
        setMessage("Signed in with email code.");
        return;
      }

      if (mode === "forgot") {
        await request(`${AUTH_URL}/auth/forgot-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username,
            email,
            new_password: newPassword,
          }),
        });
        setMode("login");
        setPassword("");
        setNewPassword("");
        setMessage("Password reset. Log in with the new password.");
        return;
      }

      const endpoint = mode === "signup" ? "signup" : "login";
      const payload =
        mode === "signup"
          ? { username, email, password, role }
          : { username, password };
      const data = await request(`${AUTH_URL}/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      storeSession(data);
      setMessage(mode === "signup" ? "Account created." : "Signed in.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const title =
    mode === "signup"
      ? "Sign Up"
      : mode === "email-code"
        ? "Email Code"
      : mode === "forgot"
        ? "Reset Password"
        : "Log In";
  const submitLabel = mode === "email-code" ? "Log In" : title;
  const needsEmail =
    mode === "signup" || mode === "forgot" || mode === "email-code";
  const needsUsername = mode !== "email-code";
  const submitDisabled =
    submitting ||
    (needsUsername && !username) ||
    (mode !== "forgot" && mode !== "email-code" && !password) ||
    (needsEmail && !email) ||
    (mode === "forgot" && !newPassword) ||
    (mode === "email-code" && !verificationCode);
  const requestCodeDisabled = submitting || !email;

  return (
    <section className="panel auth-panel">
      <div className="panel-head">
        <h2>{title}</h2>
        <span>{session ? session.role : "choose your role"}</span>
      </div>
      <div className="auth-tabs">
        <button
          className={mode === "login" ? "active" : ""}
          onClick={() => switchMode("login")}
          type="button"
        >
          Log In
        </button>
        <button
          className={mode === "signup" ? "active" : ""}
          onClick={() => switchMode("signup")}
          type="button"
        >
          Sign Up
        </button>
        <button
          className={mode === "email-code" ? "active" : ""}
          onClick={() => switchMode("email-code")}
          type="button"
        >
          Email Code
        </button>
        <button
          className={mode === "forgot" ? "active" : ""}
          onClick={() => switchMode("forgot")}
          type="button"
        >
          Forgot
        </button>
      </div>
      {mode === "signup" || mode === "email-code" ? (
        <div className="role-choice">
          <button
            className={role === "kitten" ? "role-card active" : "role-card"}
            onClick={() => setRole("kitten")}
            type="button"
          >
            <strong>Kitten</strong>
            <span>Solve problems, fish, collect, trade, and rank.</span>
          </button>
          <button
            className={role === "cat" ? "role-card active" : "role-card"}
            onClick={() => setRole("cat")}
            type="button"
          >
            <strong>Cat</strong>
            <span>Create fish ponds and coding problems for kittens.</span>
          </button>
        </div>
      ) : null}
      <div className="form-grid two-cols">
        {needsUsername ? (
          <label>
            Username
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
        ) : null}
        {needsEmail ? (
          <label>
            Email
            <input
              value={email}
              type="email"
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
        ) : null}
        {mode === "email-code" ? (
          <label>
            Verification code
            <input
              value={verificationCode}
              inputMode="numeric"
              onChange={(event) => setVerificationCode(event.target.value)}
            />
          </label>
        ) : mode !== "forgot" ? (
          <label>
            Password
            <input
              value={password}
              type="password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        ) : (
          <label>
            New password
            <input
              value={newPassword}
              type="password"
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </label>
        )}
      </div>
      <div className="button-row">
        {mode === "email-code" ? (
          <button
            className="secondary-button"
            disabled={requestCodeDisabled}
            onClick={requestEmailCode}
            type="button"
          >
            Send Code
          </button>
        ) : null}
        <button disabled={submitDisabled} onClick={submitAuth}>
          {submitting ? "Working..." : submitLabel}
        </button>
      </div>
      <Status error={error} message={message} />
    </section>
  );
}

function LoginScreen({ session, setSession }) {
  return (
    <main className="login-screen">
      <section className="login-copy">
        <img className="hero-logo" src={catchLogo} alt="CatCh" />
        <h1>Code, fish, and learn.</h1>
        <p>
          Kittens play the coding game economy. Cats create ponds and problems
          without joining the token system.
        </p>
      </section>
      <AuthPanel session={session} setSession={setSession} />
    </main>
  );
}

function QuizPanel({ userId, refreshInventory }) {
  const [channels, setChannels] = useState({ public: [], private: [] });
  const [channelMode, setChannelMode] = useState("public");
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [problem, setProblem] = useState(null);
  const [code, setCode] = useState("");
  const [result, setResult] = useState(null);
  const [uncaught, setUncaught] = useState([]);
  const [uncaughtDetail, setUncaughtDetail] = useState(null);
  const [roomCode, setRoomCode] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [joining, setJoining] = useState(false);
  const [resetting, setResetting] = useState(false);

  const visibleChannels = channels[channelMode] || [];
  const selectedProblems = selectedChannel?.problems || [];
  const allDone =
    selectedProblems.length > 0 && selectedProblems.every((item) => item.completed);

  async function refreshChannels() {
    const data = await request(`${GAME_URL}/quiz/channels/${userId}`);
    setChannels(data);
    if (selectedChannel) {
      const current = [...data.public, ...data.private].find(
        (channel) => channel.pond_id === selectedChannel.pond_id,
      );
      setSelectedChannel(current || null);
      return current || null;
    }
    return null;
  }

  async function refreshUncaught() {
    const data = await request(`${GAME_URL}/quiz/uncaught/${userId}`);
    setUncaught(data);
  }

  function selectChannel(channel) {
    setSelectedChannel(channel);
    setProblem(null);
    setUncaughtDetail(null);
    setResult(null);
    setMessage("");
    setError("");
  }

  useEffect(() => {
    refreshChannels().catch((err) => setError(err.message));
    refreshUncaught().catch(() => {});
  }, [userId]);

  async function selectProblem(problemId) {
    setResult(null);
    setUncaughtDetail(null);
    setError("");
    try {
      const data = await request(`${GAME_URL}/quiz/problems/${problemId}`);
      setProblem(data);
      setCode(data.starter_code);
    } catch (err) {
      setError(err.message);
    }
  }

  async function selectUncaught(item) {
    setResult(null);
    setProblem(null);
    setMessage("");
    setError("");
    try {
      const data = await request(`${GAME_URL}/quiz/problems/${item.problem_id}`);
      setUncaughtDetail({ ...item, problem: data });
    } catch (err) {
      setUncaughtDetail(item);
      setError(err.message);
    }
  }

  async function joinPrivateRoom() {
    if (!roomCode.trim()) return;
    setError("");
    setMessage("");
    setJoining(true);
    try {
      const joined = await request(`${GAME_URL}/ponds/private/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, room_code: roomCode }),
      });
      const data = await request(`${GAME_URL}/quiz/channels/${userId}`);
      setChannels(data);
      const channel = data.private.find((item) => item.pond_id === joined.pond_id);
      if (channel) {
        setChannelMode("private");
        selectChannel(channel);
      }
      setRoomCode("");
      setMessage("Private room joined.");
    } catch (err) {
      setError(err.message);
    } finally {
      setJoining(false);
    }
  }

  async function resetSelectedChannel() {
    if (!selectedProblems.length) return;
    setError("");
    setMessage("");
    setResetting(true);
    try {
      await request(`${GAME_URL}/quiz/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          problem_ids: selectedProblems.map((item) => item.id),
        }),
      });
      await refreshChannels();
      setProblem(null);
      setResult(null);
      setMessage("Quiz reset. Start again from the list.");
    } catch (err) {
      setError(err.message);
    } finally {
      setResetting(false);
    }
  }

  async function submitCode() {
    if (!problem) return;
    setError("");
    setSubmitting(true);
    try {
      const data = await request(`${GAME_URL}/quiz/problems/${problem.id}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, code, language: "python" }),
      });
      setResult(data);
      await refreshInventory();
      await refreshUncaught();
      const refreshedChannel = await refreshChannels();
      if (data.passed) {
        const nextProblem = (refreshedChannel?.problems || []).find(
          (item) => !item.completed && item.id !== problem.id,
        );
        if (nextProblem) {
          await selectProblem(nextProblem.id);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="workbench">
      <aside className="list-pane">
        <details className="quiz-menu" open>
          <summary>Quiz</summary>
          <button
            className={channelMode === "public" ? "list-item active" : "list-item"}
            onClick={() => {
              setChannelMode("public");
              setSelectedChannel(null);
              setProblem(null);
              setUncaughtDetail(null);
            }}
          >
            Public
          </button>
          <button
            className={channelMode === "private" ? "list-item active" : "list-item"}
            onClick={() => {
              setChannelMode("private");
              setSelectedChannel(null);
              setProblem(null);
              setUncaughtDetail(null);
            }}
          >
            Private
          </button>
        </details>

        {channelMode === "private" ? (
          <div className="room-search">
            <input
              placeholder="Private room code"
              value={roomCode}
              onChange={(event) => setRoomCode(event.target.value.toUpperCase())}
            />
            <button disabled={joining || !roomCode.trim()} onClick={joinPrivateRoom}>
              {joining ? "Joining..." : "Join"}
            </button>
          </div>
        ) : null}

        <strong className="channel-title">
          {channelMode === "public" ? "Public Ponds" : "Private Ponds"}
        </strong>
        {visibleChannels.length === 0 ? (
          <span className="muted">
            {channelMode === "private"
              ? "Enter a private room code to join a classroom."
              : "No public ponds yet."}
          </span>
        ) : null}
        {visibleChannels.map((channel) => (
          <button
            className={
              selectedChannel?.pond_id === channel.pond_id
                ? "pond-card active"
                : "pond-card"
            }
            key={channel.pond_id}
            onClick={() => selectChannel(channel)}
          >
            <strong>{channel.name}</strong>
            <span>
              {channel.pinned ? "system" : channel.room_code || channelMode} ·{" "}
              {(channel.problems || []).length} problems
            </span>
          </button>
        ))}

        {selectedChannel ? (
          <>
            <strong className="channel-title">{selectedChannel.name}</strong>
            {selectedProblems.length === 0 ? (
              <span className="muted">No problems in this pond yet.</span>
            ) : null}
            {selectedProblems.map((item) => (
              <button
                className={
                  problem?.id === item.id ? "list-item active" : "list-item"
                }
                key={item.id}
                onClick={() => selectProblem(item.id)}
              >
                <strong>
                  {item.completed ? "✓ " : ""}
                  {item.exhausted ? "x " : ""}
                  {item.title}
                </strong>
                <span>
                  {item.difficulty} · reward {item.fishing_reward} · attempts{" "}
                  {item.attempts_used}
                </span>
              </button>
            ))}
          </>
        ) : null}

        <strong className="channel-title">Uncaught Fish</strong>
        {uncaught.length === 0 ? (
          <span className="muted">Wrong-answer notebook is empty.</span>
        ) : (
          uncaught.map((item) => (
            <button
              className={
                uncaughtDetail?.problem_id === item.problem_id
                  ? "list-item active"
                  : "list-item"
              }
              key={item.problem_id}
              onClick={() => selectUncaught(item)}
            >
              <strong>x {item.title}</strong>
              <span>{item.attempts_used} attempts used</span>
            </button>
          ))
        )}
      </aside>
      <section className="panel">
        {uncaughtDetail ? (
          <>
            <div className="panel-head">
              <h2>{uncaughtDetail.title}</h2>
              <span>{uncaughtDetail.attempts_used} failed attempts</span>
            </div>
            <pre className="instructions">
              {uncaughtDetail.instructions ||
                uncaughtDetail.problem?.instructions ||
                "Problem prompt unavailable."}
            </pre>
            <h3>Correct Answer</h3>
            <pre className="solution">{uncaughtDetail.solution_code}</pre>
            {uncaughtDetail.solution_explanation ? (
              <p className="subtle-text">{uncaughtDetail.solution_explanation}</p>
            ) : null}
          </>
        ) : selectedChannel && allDone ? (
          <div className="empty done-state">
            <strong>{selectedChannel.name} complete.</strong>
            <span>All problems are checked off.</span>
            <button disabled={resetting} onClick={resetSelectedChannel}>
              {resetting ? "Resetting..." : "Try again"}
            </button>
          </div>
        ) : problem ? (
          <>
            <div className="panel-head">
              <h2>{problem.title}</h2>
              <span>
                {result
                  ? `${result.attempts_remaining} attempts left`
                  : `${problem.max_attempts} attempts`}
              </span>
            </div>
            <pre className="instructions">{problem.instructions}</pre>
            <textarea
              className="code-box"
              spellCheck="false"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            <button disabled={submitting} onClick={submitCode}>
              {submitting ? "Checking..." : "Submit"}
            </button>
            {result ? (
              <div className={result.passed ? "result pass" : "result"}>
                <strong>{result.passed ? "Passed" : "Not passed"}</strong>
                <span>
                  {result.tests_passed}/{result.tests_run} tests · fishing reward{" "}
                  {result.fishing_reward_granted}
                </span>
                {result.tokens_lost ? (
                  <span>Lost {result.tokens_lost} Cat Can Token.</span>
                ) : null}
                {result.solution_revealed ? (
                  <pre className="solution">{result.solution_code}</pre>
                ) : null}
              </div>
            ) : null}
          </>
        ) : (
          <div className="empty">
            {selectedChannel
              ? "Select a problem to start."
              : "Choose Public or Private, then open a pond."}
          </div>
        )}
        <Status error={error} message={message} />
      </section>
    </section>
  );
}

function FishingPanel({ userId, inventory, refreshInventory }) {
  const [lastFish, setLastFish] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [casting, setCasting] = useState(false);

  async function cast() {
    setError("");
    setMessage("");
    setCasting(true);
    try {
      const data = await request(`${GAME_URL}/fishing/cast?user_id=${userId}`, {
        method: "POST",
      });
      setLastFish(data.fish);
      setMessage(`Fishing complete. ${data.remaining_chances} chances left.`);
      await refreshInventory();
    } catch (err) {
      setError(err.message);
    } finally {
      setCasting(false);
    }
  }

  async function sellFish(fishId) {
    setError("");
    setMessage("");
    try {
      const data = await request(
        `${GAME_URL}/fishing/sell/${fishId}?user_id=${userId}`,
        { method: "POST" },
      );
      setMessage(`Sold common fish for ${data.tokens_earned} tokens.`);
      await refreshInventory();
    } catch (err) {
      setError(err.message);
    }
  }

  const canCast = inventory.fishing_chances > 0 && !casting;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Fish</h2>
        <span>{inventory.fishing_chances} chances</span>
      </div>
      <div className="cast-strip">
        <button onClick={cast} disabled={!canCast}>
          {casting ? "Fishing..." : "Fish"}
        </button>
        <span>
          {inventory.fishing_chances > 0
            ? "Each fish attempt consumes 1 fishing chance and uses the fish dataset."
            : "Solve a quiz problem correctly to earn a fishing chance."}
        </span>
      </div>
      {lastFish ? (
        <div className="fish-highlight">
          <img src={imageUrl(lastFish.image_url)} alt={lastFish.species_name} />
          <div>
            <strong>{lastFish.species_name}</strong>
            <span>
              {lastFish.rarity} · {lastFish.quality} · {lastFish.size_cm} cm
            </span>
            <p>{lastFish.description}</p>
          </div>
        </div>
      ) : null}
      <Status error={error} message={message} />
      <div className="card-grid">
        {inventory.fish.map((fish) => (
          <article className="fish-card" key={fish.fish_id}>
            <img src={imageUrl(fish.image_url)} alt={fish.species_name} />
            <strong>{fish.species_name}</strong>
            <span>
              {fish.rarity} · {fish.quality} · {fish.size_cm} cm
            </span>
            {fish.rarity === "common" ? (
              <button onClick={() => sellFish(fish.fish_id)}>
                Sell for {fish.sell_value_tokens || fish.sell_value} Tokens
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function AquariumPanel({ userId }) {
  const [aquarium, setAquarium] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    request(`${GAME_URL}/aquarium/${userId}`)
      .then(setAquarium)
      .catch((err) => setError(err.message));
  }, [userId]);

  if (!aquarium) {
    return (
      <section className="panel">
        <div className="panel-head">
          <h2>Aquarium Collection</h2>
          <span>Loading collection...</span>
        </div>
        <Status error={error} />
      </section>
    );
  }

  const collected = aquarium.collected_species || 0;
  const total = aquarium.total_species || 50;
  const percentage = aquarium.collection_percentage || 0;

  return (
    <section className="panel aquarium-panel">
      <div className="panel-head">
        <div>
          <h2>Aquarium Collection</h2>
          <p className="subtle-text">
            Your medal wall: collect unique fish species to grow your aquarium.
          </p>
        </div>
        <span>{percentage}% collected</span>
      </div>

      <div className="collection-summary">
        <div>
          <strong>{collected}</strong>
          <span>Species collected</span>
        </div>
        <div>
          <strong>{total - collected}</strong>
          <span>Species left</span>
        </div>
        <div>
          <strong>{aquarium.fish.length}</strong>
          <span>Unique fish shown</span>
        </div>
      </div>

      <div className="progress-track labeled">
        <div style={{ width: `${percentage}%` }} />
      </div>

      {aquarium.fish.length === 0 ? (
        <div className="aquarium-empty">
          <strong>No fish collected yet.</strong>
          <span>Solve quiz problems to earn fishing chances, then start collecting.</span>
        </div>
      ) : (
        <div className="aquarium-stage">
          {aquarium.fish.map((fish, index) => (
            <button
              className="swimmer"
              key={fish.species_id}
              style={{
                top: `${14 + (index % 6) * 12}%`,
                animationDelay: `${index * -1.25}s`,
              }}
              title={`${fish.species_name}, quantity ${fish.quantity}`}
              type="button"
            >
              <img src={imageUrl(fish.image_url)} alt={fish.species_name} />
              <span>x{fish.quantity}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function MarketPanel({ inventory, userId, refreshInventory }) {
  const [listings, setListings] = useState([]);
  const [priceByFish, setPriceByFish] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function refreshListings() {
    try {
      setListings(await request(`${GAME_URL}/market/listings`));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refreshListings();
  }, [userId]);

  async function listFish(fish) {
    setError("");
    setMessage("");
    // Fall back to the fish's suggested price when the user hasn't typed a value —
    // the input shows suggested_price as a placeholder, but priceByFish is empty
    // until the user touches it. Without this fallback the request sent 1.
    const typed = priceByFish[fish.fish_id];
    const price = Number(typed != null && typed !== "" ? typed : fish.suggested_price);
    try {
      await request(`${GAME_URL}/market/list`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          fish_id: fish.fish_id,
          price,
        }),
      });
      refreshListings();
      refreshInventory();
      setMessage(`${fish.species_name} listed for ${price} tokens.`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function buy(listingId) {
    setError("");
    setMessage("");
    try {
      await request(`${GAME_URL}/market/buy/${listingId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ buyer_id: userId }),
      });
      refreshListings();
      refreshInventory();
      setMessage("Trade complete. The fish moved into your inventory.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function unlist(listingId) {
    setError("");
    setMessage("");
    try {
      await request(
        `${GAME_URL}/market/listings/${listingId}?seller_id=${encodeURIComponent(userId)}`,
        { method: "DELETE" },
      );
      refreshListings();
      refreshInventory();
      setMessage("Listing cancelled. Fish returned to your inventory.");
    } catch (err) {
      setError(err.message);
    }
  }

  const marketFish = inventory.fish.filter((fish) => fish.rarity !== "common");
  const myListings = listings.filter((l) => l.seller_id === userId);

  return (
    <section className="workbench two">
      <section className="panel">
        <div className="panel-head">
          <h2>Your Market Fish</h2>
          <span>{inventory.tokens} tokens</span>
        </div>
        <p className="market-note">
          Only uncommon or rarer fish can be sold on the marketplace. Common fish
          can be sold directly for their sell value.
        </p>
        {marketFish.length === 0 && myListings.length === 0 ? (
          <div className="empty">
            <span>No marketplace fish in inventory.</span>
          </div>
        ) : null}
        {marketFish.map((fish) => (
          <div className="market-row" key={fish.fish_id}>
            <div className="market-fish">
              <img src={imageUrl(fish.image_url)} alt={fish.species_name} />
              <span>
                {fish.species_name}
                <small>{fish.rarity} · suggested {fish.suggested_price}</small>
              </span>
            </div>
            <input
              type="number"
              min="1"
              value={priceByFish[fish.fish_id] ?? fish.suggested_price}
              onChange={(event) =>
                setPriceByFish({ ...priceByFish, [fish.fish_id]: event.target.value })
              }
            />
            <button onClick={() => listFish(fish)}>List Fish</button>
          </div>
        ))}
        {myListings.length > 0 ? (
          <>
            <h3>Your Listings</h3>
            {myListings.map((listing) => (
              <div className="market-row" key={listing.listing_id}>
                <div className="market-fish">
                  <img
                    src={imageUrl(listing.fish.image_url)}
                    alt={listing.fish.species_name}
                  />
                  <span>
                    {listing.fish.species_name}
                    <small>public listing</small>
                  </span>
                </div>
                <strong>{listing.price} tokens</strong>
                <button onClick={() => unlist(listing.listing_id)}>Cancel</button>
              </div>
            ))}
          </>
        ) : null}
      </section>
      <section className="panel">
        <h2>Listings</h2>
        {listings.length === 0 ? (
          <p className="empty">No active fish listings yet.</p>
        ) : null}
        {listings.map((listing) => {
          const isMine = listing.seller_id === userId;
          return (
            <div className="market-row" key={listing.listing_id}>
              <div className="market-fish">
                <img
                  src={imageUrl(listing.fish.image_url)}
                  alt={listing.fish.species_name}
                />
                <span>
                  {listing.fish.species_name}
                  <small>{isMine ? "your listing" : listing.seller_id}</small>
                </span>
              </div>
              <strong>{listing.price} tokens</strong>
              {isMine ? (
                <button onClick={() => unlist(listing.listing_id)}>Cancel</button>
              ) : (
                <button onClick={() => buy(listing.listing_id)}>Buy Fish</button>
              )}
            </div>
          );
        })}
        <Status error={error} message={message} />
      </section>
    </section>
  );
}

function LeaderboardPanel() {
  const [tokens, setTokens] = useState([]);
  const [aquarium, setAquarium] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");

    Promise.all([
      request(`${GAME_URL}/leaderboard/tokens`),
      request(`${GAME_URL}/leaderboard/aquarium`),
    ])
      .then(([tokenRows, aquariumRows]) => {
        setTokens(tokenRows);
        setAquarium(aquariumRows);
      })
      .catch((err) => setError(err.message));
  }, []);

  function rankBadge(index) {
    if (index === 0) return "🥇";
    if (index === 1) return "🥈";
    if (index === 2) return "🥉";
    return `#${index + 1}`;
  }

  return (
    <section className="workbench two leaderboard-page">
      <section className="panel leaderboard-card">
        <div className="panel-head">
          <div>
            <h2>Token Leaderboard</h2>
            <p className="subtle-text">Ranks kittens by total earned tokens.</p>
          </div>
        </div>

        {tokens.length === 0 ? (
          <p className="empty">No token rankings yet.</p>
        ) : (
          <div className="rank-list">
            {tokens.map((row, index) => (
              <div className="rank-row enhanced" key={row.user_id}>
                <span className="rank-medal">{rankBadge(index)}</span>
                <span className="rank-name">{row.username || row.user_id}</span>
                <strong className="rank-value">{row.tokens} tokens</strong>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel leaderboard-card">
        <div className="panel-head">
          <div>
            <h2>Aquarium Leaderboard</h2>
            <p className="subtle-text">Ranks kittens by fish species collection progress.</p>
          </div>
        </div>

        {aquarium.length === 0 ? (
          <p className="empty">No aquarium rankings yet.</p>
        ) : (
          <div className="rank-list">
            {aquarium.map((row, index) => (
              <div className="rank-row enhanced" key={row.user_id}>
                <span className="rank-medal">{rankBadge(index)}</span>
                <span className="rank-name">
                  {row.username || row.user_id}
                  <small>
                    {row.collected_species || 0}/{row.total_species || 50} species
                  </small>
                </span>
                <strong className="rank-value">{row.collection_percentage}%</strong>
              </div>
            ))}
          </div>
        )}

        <Status error={error} />
      </section>
    </section>
  );
}

function TeacherPanel({ userId }) {
  const [name, setName] = useState("CS Pond");
  const [visibility, setVisibility] = useState("private");
  const [ponds, setPonds] = useState([]);
  const [pond, setPond] = useState(null);
  const [pondProblems, setPondProblems] = useState([]);
  const [rules, setRules] = useState(null);
  const [problem, setProblem] = useState(defaultTeacherProblem);
  const [selectedProblemId, setSelectedProblemId] = useState(null);
  const [problemResult, setProblemResult] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    request(`${TEACHER_URL}/teacher/rules`).then(setRules).catch(() => {});
    refreshTeacherPonds().catch(() => {});
  }, [userId]);

  async function refreshTeacherPonds() {
    const data = await request(`${TEACHER_URL}/teacher/${userId}/ponds`);
    setPonds(data);
    return data;
  }

  async function loadPondProblems(nextPond, resetForm = true) {
    setPond(nextPond);
    if (resetForm) {
      setProblemResult(null);
      setSelectedProblemId(null);
      setProblem(defaultTeacherProblem);
    }
    setError("");
    try {
      const data = await request(
        `${TEACHER_URL}/teacher/ponds/${nextPond.pond_id}/problems`,
      );
      setPondProblems(data);
    } catch (err) {
      setPondProblems([]);
      setError(err.message);
    }
  }

  async function createPond() {
    setError("");
    setMessage("");
    setProblemResult(null);
    try {
      const data = await request(`${TEACHER_URL}/teacher/ponds`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cat_id: userId,
          name,
          visibility,
          description: "Teacher-created fish pond",
        }),
      });
      setPond(null);
      setPondProblems([]);
      await refreshTeacherPonds();
      setMessage(`${data.name} created. Click the classroom to add problems.`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createProblem() {
    if (!pond?.pond_id) {
      setError("Create a fish pond before adding a problem.");
      return;
    }
    setError("");
    setMessage("");
    try {
      const payload = {
        cat_id: userId,
        ...problem,
      };
      const method = selectedProblemId ? "PUT" : "POST";
      const path = selectedProblemId
        ? `${TEACHER_URL}/teacher/ponds/${pond.pond_id}/problems/${selectedProblemId}`
        : `${TEACHER_URL}/teacher/ponds/${pond.pond_id}/problems`;
      const data = await request(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          selectedProblemId ? payload : { ...payload, pond_id: pond.pond_id },
        ),
      });
      setProblemResult(data);
      if (data.problem?.id) {
        selectTeacherProblem(data.problem);
      }
      await loadPondProblems(pond, false);
      setMessage(selectedProblemId ? "Problem updated." : "Problem created.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteProblem() {
    if (!pond?.pond_id || !selectedProblemId) return;
    setError("");
    setMessage("");
    try {
      await request(
        `${TEACHER_URL}/teacher/ponds/${pond.pond_id}/problems/${selectedProblemId}` +
          `?cat_id=${encodeURIComponent(userId)}`,
        { method: "DELETE" },
      );
      setSelectedProblemId(null);
      setProblem(defaultTeacherProblem);
      setProblemResult(null);
      await loadPondProblems(pond);
      setMessage("Problem deleted.");
    } catch (err) {
      setError(err.message);
    }
  }

  function selectTeacherProblem(item) {
    setSelectedProblemId(item.id);
    setProblemResult(null);
    setMessage("");
    setError("");
    setProblem({
      title: item.title || "",
      prompt: item.instructions || "",
      starter_code: item.starter_code || "",
      reference_solution: item.solution_code || "",
      test_code: item.test_code || "",
      topic: item.topic || "",
    });
  }

  function startNewProblem() {
    setSelectedProblemId(null);
    setProblem(defaultTeacherProblem);
    setProblemResult(null);
    setMessage("");
    setError("");
  }

  function updateProblem(field, value) {
    setProblem((current) => ({ ...current, [field]: value }));
  }

  return (
    <section className={pond ? "workbench two" : "workbench"}>
      <section className="panel">
        <div className="panel-head">
          <h2>Create Fish Pond</h2>
          <span>{rules?.token_system_enabled === false ? "no token system" : ""}</span>
        </div>
        <div className="form-grid two-cols">
          <label>
            Pond name
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Visibility
            <select
              value={visibility}
              onChange={(event) => setVisibility(event.target.value)}
            >
              <option value="public">Public</option>
              <option value="private">Private</option>
            </select>
          </label>
        </div>
        <button onClick={createPond}>Create Room</button>
        {pond ? (
          <div className="result pass">
            <strong>{pond.name}</strong>
            <span>
              {pond.visibility} · room code {pond.room_code || "none"}
            </span>
          </div>
        ) : null}
        <div className="teacher-room-list">
          <strong className="channel-title">My Classrooms</strong>
          {ponds.length === 0 ? (
            <span className="muted">Create a classroom to add questions.</span>
          ) : null}
          {ponds.map((item) => (
            <button
              className={
                pond?.pond_id === item.pond_id ? "pond-card active" : "pond-card"
              }
              key={item.pond_id}
              onClick={() => loadPondProblems(item)}
            >
              <strong>{item.name}</strong>
              <span>
                {item.visibility} · room code {item.room_code || "none"} ·{" "}
                {(item.problem_ids || []).length} problems
              </span>
            </button>
          ))}
        </div>
        {pond ? (
          <div className="teacher-problem-list">
            <strong className="channel-title">{pond.name} Problems</strong>
            {pondProblems.length === 0 ? (
              <span className="muted">No problems in this classroom yet.</span>
            ) : null}
            {pondProblems.map((item) => (
              <button
                className={
                  selectedProblemId === item.id ? "pond-card active" : "pond-card"
                }
                key={item.id}
                onClick={() => selectTeacherProblem(item)}
              >
                <strong>{item.title}</strong>
                <span>{item.topic || item.difficulty}</span>
              </button>
            ))}
          </div>
        ) : null}
        <Status error={error} message={message} />
      </section>
      {pond ? (
        <section className="panel">
          <div className="panel-head">
            <h2>{selectedProblemId ? "Edit Problem" : "Create Problem"}</h2>
            <button type="button" onClick={startNewProblem}>
              New Problem
            </button>
          </div>
          <div className="form-grid two-cols">
            <label>
              Title
              <input
                value={problem.title}
                onChange={(event) => updateProblem("title", event.target.value)}
              />
            </label>
            <label>
              Topic
              <input
                value={problem.topic}
                onChange={(event) => updateProblem("topic", event.target.value)}
              />
            </label>
          </div>
          <label>
            Prompt
            <textarea
              value={problem.prompt}
              onChange={(event) => updateProblem("prompt", event.target.value)}
            />
          </label>
          <label>
            Starter code
            <textarea
              className="code-box small"
              value={problem.starter_code}
              onChange={(event) => updateProblem("starter_code", event.target.value)}
            />
          </label>
          <label>
            Reference solution
            <textarea
              className="code-box small"
              value={problem.reference_solution}
              onChange={(event) =>
                updateProblem("reference_solution", event.target.value)
              }
            />
          </label>
          <label>
            Test code
            <textarea
              className="code-box small"
              value={problem.test_code}
              onChange={(event) => updateProblem("test_code", event.target.value)}
            />
          </label>
          <div className="button-row">
            <button onClick={createProblem}>
              {selectedProblemId ? "Update Problem" : "Create Problem"}
            </button>
            {selectedProblemId ? (
              <button className="danger-button" onClick={deleteProblem}>
                Delete Problem
              </button>
            ) : null}
          </div>
          {problemResult ? (
            <div className="result pass">
              <strong>{problem.title}</strong>
              <span>{problemResult.status || "created"}</span>
            </div>
          ) : null}
          <Status error={error} />
        </section>
      ) : null}
    </section>
  );
}

export default function App() {
  const [session, setSession] = useState(loadStoredSession);
  const [activeTab, setActiveTab] = useState("quiz");
  const [inventory, setInventory] = useState(emptyInventory("demo_user"));
  const [rules, setRules] = useState(null);

  const role = session?.role;
  const userId = session?.user_id || "";
  const tabs = role === "cat" ? catTabs : kittenTabs;
  const activeLabel = tabs.find(([id]) => id === activeTab)?.[1] || tabs[0][1];

  function logout() {
    request(`${AUTH_URL}/auth/logout`, { method: "POST" }).catch(() => {});
    localStorage.removeItem("catch_user_id");
    localStorage.removeItem("catch_role");
    localStorage.removeItem("catch_token");
    localStorage.removeItem("catch_username");
    localStorage.removeItem("catch_session_version");
    setSession(null);
    setActiveTab("quiz");
    setInventory(emptyInventory("demo_user"));
  }

  async function refreshInventory() {
    if (!userId || role !== "kitten") return;
    const data = await request(`${GAME_URL}/fishing/inventory/${userId}`);
    setInventory(data);
  }

  useEffect(() => {
    if (!session) return;
    setActiveTab(session.role === "cat" ? "teacher" : "quiz");
  }, [session?.role]);

  useEffect(() => {
    if (!session) return;
    if (role === "kitten") {
      refreshInventory().catch(() => {});
    } else {
      setInventory(emptyInventory(userId));
    }
    request(`${INTEGRATION_URL}/integration/product-rules`)
      .then(setRules)
      .catch(() => {});
  }, [userId, role]);

  const tabContent = useMemo(() => {
    if (role === "cat") {
      return <TeacherPanel userId={userId} />;
    }
    if (activeTab === "quiz") {
      return <QuizPanel userId={userId} refreshInventory={refreshInventory} />;
    }
    if (activeTab === "fishing") {
      return (
        <FishingPanel
          userId={userId}
          inventory={inventory}
          refreshInventory={refreshInventory}
        />
      );
    }
    if (activeTab === "aquarium") return <AquariumPanel userId={userId} />;
    if (activeTab === "market") {
      return (
        <MarketPanel
          inventory={inventory}
          userId={userId}
          refreshInventory={refreshInventory}
        />
      );
    }
    return <LeaderboardPanel />;
  }, [activeTab, inventory, role, userId]);

  if (!session) {
    return <LoginScreen session={session} setSession={setSession} />;
  }

  return (
    <main className="app-shell">
      <aside className="nav">
        <div className="brand">
          <img className="nav-logo" src={catchLogo} alt="CatCh" />
          <span>{role === "cat" ? "Cat teacher" : "Kitten programmer"}</span>
          <span>{session.username || userId}</span>
        </div>
        {tabs.map(([id, label]) => (
          <button
            className={activeTab === id ? "nav-button active" : "nav-button"}
            key={id}
            onClick={() => setActiveTab(id)}
          >
            {label}
          </button>
        ))}
        <button className="nav-button logout" onClick={logout}>
          Log out
        </button>
      </aside>
      <section className="content">
        <header className="topbar">
          <div>
            <h1>{activeLabel}</h1>
            <p>{rules?.name || "CatCh: Code, Fish, and Learn"}</p>
          </div>
          {role === "kitten" ? (
            <div className="quick-stats">
              <span>Chances {inventory.fishing_chances}</span>
              <span>Tokens {inventory.tokens}</span>
              <span>Fish {inventory.total_count}</span>
            </div>
          ) : (
            <div className="quick-stats">
              <span>Teacher mode</span>
              <span>No tokens</span>
            </div>
          )}
        </header>
        {tabContent}
      </section>
    </main>
  );
}
