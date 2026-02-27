#!/usr/bin/env node
/**
 * QA Browser Test Harness — End-to-end orchestrator
 *
 * Creates a codespace, starts the app, runs Claude with the QA tester agent,
 * and reports results. Each iteration takes ~5-10 min instead of 90 min.
 *
 * Usage:
 *   node scripts/test-qa-harness.js [--skip-cleanup] [--machine <type>]
 *
 * Requirements:
 *   - gh CLI authenticated
 *   - ANTHROPIC_API_KEY set (or codespace secret)
 */

const { execSync, spawn } = require("child_process");

// ── Config ──────────────────────────────────────────────────────────────────

const REPO = "dreamteam-ai-labs/browser-agent-test-fixture";
const DEFAULT_MACHINE = "basicLinux32gb";
const GH_CONFIG_DIR =
  process.env.GH_CONFIG_DIR ||
  "D:/OneDrive/Physical Devices/Fireblade/Documents/Software Projects/Config/.gh-dreamteam";

const args = process.argv.slice(2);
const SKIP_CLEANUP = args.includes("--skip-cleanup");
const machineIdx = args.indexOf("--machine");
const MACHINE = machineIdx >= 0 ? args[machineIdx + 1] : DEFAULT_MACHINE;

// ── Helpers ─────────────────────────────────────────────────────────────────

function gh(cmd, opts = {}) {
  const fullCmd = `GH_CONFIG_DIR="${GH_CONFIG_DIR}" gh ${cmd}`;
  const result = execSync(fullCmd, {
    encoding: "utf-8",
    timeout: opts.timeout || 120_000,
    stdio: opts.stdio || "pipe",
    ...opts,
  });
  return result.trim();
}

function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`[${ts}] ${msg}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Main ────────────────────────────────────────────────────────────────────

async function main() {
  let codespace = null;

  try {
    // Step 1: Create codespace
    log("STEP 1: Creating codespace...");
    const createResult = gh(
      `codespace create --repo ${REPO} --machine ${MACHINE} --status`,
      { timeout: 180_000 }
    );
    codespace = createResult.trim();
    log(`  Codespace: ${codespace}`);

    // Step 2: Wait for codespace to be ready
    log("STEP 2: Waiting for codespace to be ready...");
    let ready = false;
    for (let i = 0; i < 30; i++) {
      await sleep(10_000);
      try {
        const status = gh(
          `codespace view -c ${codespace} --json state -q ".state"`
        );
        log(`  Status: ${status}`);
        if (status === "Available") {
          ready = true;
          break;
        }
      } catch (e) {
        log(`  Check failed: ${e.message}`);
      }
    }
    if (!ready) {
      throw new Error("Codespace did not become Available within 5 minutes");
    }

    // Step 3: Wait for post-start to finish + verify services
    log("STEP 3: Verifying services...");
    await sleep(15_000); // Give post-start time to run

    for (let i = 0; i < 6; i++) {
      try {
        const health = gh(
          `codespace ssh -c ${codespace} -- curl -s http://localhost:8000/api/health`
        );
        log(`  Backend health: ${health}`);
        if (health.includes("healthy")) break;
      } catch (e) {
        log(`  Backend not ready yet (attempt ${i + 1}/6)...`);
        await sleep(10_000);
      }
    }

    // Step 4: Make ports public
    log("STEP 4: Making ports public...");
    try {
      gh(
        `codespace ports visibility 8000:public 3000:public -c ${codespace}`
      );
      log("  Ports 8000 and 3000 set to public");
    } catch (e) {
      log(`  Warning: port visibility failed: ${e.message}`);
    }

    // Step 5: Run Claude with QA tester
    log("STEP 5: Running Claude Code with QA tester...");
    log("  This will stream output in real-time...");
    log("─".repeat(60));

    const claudeCmd = [
      "claude",
      "-p",
      `Read CLAUDE.md and features.json. Then spawn the qa-tester agent (@qa-tester). Wait for the QA tester to complete all test steps including the browser smoke test. Report the final results.`,
      "--allowedTools",
      "Bash,Read,Write,Edit,Glob,Grep",
      "--output-format",
      "text",
    ].join(" ");

    // Use SSH to run Claude in the codespace
    const sshProc = spawn(
      "gh",
      [
        "codespace",
        "ssh",
        "-c",
        codespace,
        "--",
        "bash",
        "-l",
        "-c",
        `cd /workspaces/browser-agent-test-fixture && ${claudeCmd}`,
      ],
      {
        env: { ...process.env, GH_CONFIG_DIR },
        stdio: ["ignore", "pipe", "pipe"],
        timeout: 600_000, // 10 min
      }
    );

    let claudeOutput = "";

    sshProc.stdout.on("data", (data) => {
      const text = data.toString();
      claudeOutput += text;
      process.stdout.write(text);
    });

    sshProc.stderr.on("data", (data) => {
      process.stderr.write(data.toString());
    });

    await new Promise((resolve, reject) => {
      sshProc.on("close", (code) => {
        log("─".repeat(60));
        log(`Claude exited with code: ${code}`);
        resolve(code);
      });
      sshProc.on("error", reject);
    });

    // Step 6: Retrieve results
    log("STEP 6: Retrieving results...");

    try {
      const results = gh(
        `codespace ssh -c ${codespace} -- cat /workspaces/browser-agent-test-fixture/qa-smoke-results.json`
      );
      log("qa-smoke-results.json:");
      console.log(results);

      const parsed = JSON.parse(results);
      const authOk = parsed.auth?.success ? "PASS" : "FAIL";
      const browserOverall = (
        parsed.browser_smoke_test?.overall || "unknown"
      ).toUpperCase();

      log("");
      log("═".repeat(60));
      log(`  AUTH: ${authOk}  |  BROWSER: ${browserOverall}`);

      if (parsed.browser_smoke_test?.screenshotUrls) {
        log("  Screenshots:");
        for (const url of parsed.browser_smoke_test.screenshotUrls) {
          log(`    ${url}`);
        }
      }
      log("═".repeat(60));
    } catch (e) {
      log(`  Could not read results: ${e.message}`);
    }

    try {
      const report = gh(
        `codespace ssh -c ${codespace} -- cat /workspaces/browser-agent-test-fixture/qa-report.json`
      );
      log("qa-report.json:");
      console.log(report);
    } catch (e) {
      log(`  No qa-report.json found: ${e.message}`);
    }
  } catch (e) {
    log(`ERROR: ${e.message}`);
    process.exitCode = 1;
  } finally {
    // Cleanup
    if (codespace && !SKIP_CLEANUP) {
      log("CLEANUP: Deleting codespace...");
      try {
        gh(`codespace delete -c ${codespace} --force`);
        log("  Codespace deleted");
      } catch (e) {
        log(`  Cleanup failed: ${e.message}`);
      }
    } else if (codespace) {
      log(`SKIP CLEANUP: Codespace ${codespace} left running`);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
