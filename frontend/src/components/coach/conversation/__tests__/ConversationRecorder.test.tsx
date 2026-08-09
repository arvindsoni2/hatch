import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode, useLayoutEffect, type ReactNode } from "react";

const api = vi.hoisted(() => ({
  uploadCoachAttemptAudio: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, ...api };
});

import { ConversationRecorder, type ConversationRecorderProps } from "../ConversationRecorder";

class FakeTrack {
  stop = vi.fn();
}

class FakeStream {
  readonly track = new FakeTrack();

  getTracks() {
    return [this.track];
  }
}

let analyserDb = -52;
let latestAudioContext: FakeAudioContext | null = null;

class FakeAudioContext {
  state = "running";
  readonly close = vi.fn(async () => {
    this.state = "closed";
  });
  readonly source = { connect: vi.fn(), disconnect: vi.fn() };
  readonly analyser = {
    fftSize: 0,
    disconnect: vi.fn(),
    getFloatTimeDomainData: (values: Float32Array) => {
      values.fill(10 ** (analyserDb / 20));
    },
  };

  constructor() {
    latestAudioContext = this;
  }

  createMediaStreamSource() {
    return this.source;
  }

  createAnalyser() {
    return this.analyser;
  }
}

class FakeMediaRecorder {
  static latest: FakeMediaRecorder | null = null;
  static deferStop = false;

  state: RecordingState = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readonly pause = vi.fn(() => {
    if (this.state !== "recording") throw new DOMException("Invalid state", "InvalidStateError");
    this.state = "paused";
  });
  readonly resume = vi.fn(() => {
    if (this.state !== "paused") throw new DOMException("Invalid state", "InvalidStateError");
    this.state = "recording";
  });
  readonly start = vi.fn(() => {
    this.state = "recording";
  });
  readonly stop = vi.fn(() => {
    if (this.state === "inactive") return;
    this.state = "inactive";
    if (!FakeMediaRecorder.deferStop) this.completeStop();
  });

  constructor(_stream: MediaStream) {
    FakeMediaRecorder.latest = this;
  }

  emitChunk(blob: Blob) {
    this.ondataavailable?.({ data: blob } as BlobEvent);
  }

  completeStop(blob = new Blob(["final"], { type: this.mimeType })) {
    this.emitChunk(blob);
    this.onstop?.();
  }

  emitError() {
    this.onerror?.(new Event("error"));
  }
}

function installMedia() {
  const stream = new FakeStream();
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
  });
  Object.defineProperty(window, "MediaRecorder", {
    configurable: true,
    value: FakeMediaRecorder,
  });
  Object.defineProperty(window, "AudioContext", {
    configurable: true,
    value: FakeAudioContext,
  });
  return stream;
}

function props(overrides: Partial<ConversationRecorderProps> = {}): ConversationRecorderProps {
  return {
    sessionId: "session-1",
    attemptId: null,
    serverState: "asking",
    authorityAvailable: true,
    authorityVersion: 3,
    allowedCommands: ["begin_answer"],
    silencePolicy: { warning_ms: 4000, finish_prompt_ms: 9000 },
    pending: false,
    onBeginAudio: vi.fn().mockResolvedValue({ attemptId: "attempt-1", stateVersion: 4 }),
    onPause: vi.fn().mockResolvedValue("accepted"),
    onResume: vi.fn().mockResolvedValue("accepted"),
    onKeepSpeaking: vi.fn().mockResolvedValue(true),
    onCancel: vi.fn().mockResolvedValue("cancelled"),
    onDiscardAndRetry: vi.fn().mockResolvedValue(true),
    onFinishCommand: vi.fn().mockResolvedValue(true),
    onAnnouncement: vi.fn(),
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function LayoutProbe({ children, inspect }: { children: ReactNode; inspect: (() => void) | null }) {
  useLayoutEffect(() => {
    inspect?.();
  }, [inspect]);
  return children;
}

async function startRecording(
  recorderProps: ConversationRecorderProps,
  rerender: ReturnType<typeof render>["rerender"],
) {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  await user.click(screen.getByRole("button", { name: "Start audio answer" }));
  await waitFor(() => expect(FakeMediaRecorder.latest?.state).toBe("recording"));
  rerender(
    <ConversationRecorder
      {...recorderProps}
      attemptId="attempt-1"
      serverState="listening"
      authorityVersion={4}
      allowedCommands={["finish_answer", "keep_speaking", "pause", "cancel_attempt"]}
    />,
  );
  return user;
}

describe("ConversationRecorder browser capture", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    FakeMediaRecorder.latest = null;
    FakeMediaRecorder.deferStop = false;
    latestAudioContext = null;
    analyserDb = -52;
    api.uploadCoachAttemptAudio.mockResolvedValue({
      attempt_id: "attempt-1",
      upload_id: "upload-1",
      result: "completed",
      content_sha256: "a".repeat(64),
      byte_size: 5,
      mime_type: "audio/webm",
      audio_retention_state: "temporary",
      contract_version: "coach_attempt_audio_upload_v1",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reports microphone denial without removing the written-answer path", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(
          new DOMException("Permission denied", "NotAllowedError"),
        ),
      },
    });
    const user = userEvent.setup();

    render(
      <div>
        <button type="button">Answer in writing</button>
        <ConversationRecorder
          sessionId="session-1"
          attemptId={null}
          serverState="asking"
          authorityAvailable={true}
          authorityVersion={3}
          allowedCommands={["begin_answer"]}
          silencePolicy={{ warning_ms: 4000, finish_prompt_ms: 9000 }}
          pending={false}
          onBeginAudio={vi.fn()}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onKeepSpeaking={vi.fn()}
          onCancel={vi.fn()}
          onDiscardAndRetry={vi.fn()}
          onFinishCommand={vi.fn()}
          onAnnouncement={vi.fn()}
        />
      </div>,
    );

    await user.click(screen.getByRole("button", { name: "Start audio answer" }));

    expect(await screen.findByText(/microphone access was not granted/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Answer in writing" })).toBeEnabled();
  });

  it("distinguishes a missing microphone from permission denial", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(
          new DOMException("No device", "NotFoundError"),
        ),
      },
    });
    const user = userEvent.setup();
    render(<ConversationRecorder {...props()} />);

    await user.click(screen.getByRole("button", { name: "Start audio answer" }));

    expect(await screen.findByText(/no microphone was found/i)).toBeVisible();
    expect(screen.queryByText(/access was not granted/i)).not.toBeInTheDocument();
  });

  it("stops the recorder and releases the stream when audio analysis cannot start", async () => {
    const stream = installMedia();
    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      value: class UnsupportedAudioContext {
        constructor() {
          throw new DOMException("Audio analysis unavailable", "NotSupportedError");
        }
      },
    });
    const user = userEvent.setup();
    render(<ConversationRecorder {...props()} />);

    await user.click(screen.getByRole("button", { name: "Start audio answer" }));

    expect(await screen.findByText(/could not start audio capture/i)).toBeVisible();
    expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce();
    expect(stream.track.stop).toHaveBeenCalledOnce();
    expect(screen.queryByText("Microphone recording")).not.toBeInTheDocument();
  });

  it("calibrates a relative speech threshold before showing advisory silence controls", async () => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);

    act(() => vi.advanceTimersByTime(500));
    analyserDb = -25;
    act(() => vi.advanceTimersByTime(1400));
    analyserDb = -55;
    act(() => vi.advanceTimersByTime(9000));
    expect(screen.queryByText("Are you finished?")).not.toBeInTheDocument();

    analyserDb = -25;
    act(() => vi.advanceTimersByTime(1600));
    analyserDb = -55;
    act(() => vi.advanceTimersByTime(4000));
    expect(screen.getByText(/you have been quiet for a few seconds/i)).toBeVisible();
    expect(recorderProps.onAnnouncement).toHaveBeenCalledWith(
      "You have been quiet for a few seconds. Recording continues.",
    );
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText("Are you finished?")).toBeVisible();
    expect(recorderProps.onAnnouncement).toHaveBeenCalledWith(
      "Are you finished? Choose Finish answer or Keep speaking.",
    );
    expect(screen.getByRole("button", { name: "Finish answer after silence" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Keep speaking and continue recording" })).toBeEnabled();
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Keep speaking and continue recording" }));
    expect(recorderProps.onKeepSpeaking).toHaveBeenCalledWith("attempt-1");
    expect(screen.queryByText("Are you finished?")).not.toBeInTheDocument();
    expect(FakeMediaRecorder.latest?.state).toBe("recording");
  });

  it("waits for the final dataavailable chunk, uploads once, and then finishes once", async () => {
    vi.useFakeTimers();
    installMedia();
    FakeMediaRecorder.deferStop = true;
    const events: string[] = [];
    api.uploadCoachAttemptAudio.mockImplementation(async () => {
      events.push("upload");
      return {
        attempt_id: "attempt-1",
        upload_id: "upload-1",
        result: "completed",
        content_sha256: "a".repeat(64),
        byte_size: 10,
        mime_type: "audio/webm",
        audio_retention_state: "temporary",
        contract_version: "coach_attempt_audio_upload_v1",
      };
    });
    const onFinishCommand = vi.fn(async () => {
      events.push("finish");
      return true;
    });
    const recorderProps = props({ onFinishCommand });
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);
    FakeMediaRecorder.latest?.emitChunk(new Blob(["first"], { type: "audio/webm" }));

    const finish = screen.getByRole("button", { name: "Finish audio answer while recording" });
    fireEvent.click(finish);
    fireEvent.click(finish);

    expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce();
    expect(api.uploadCoachAttemptAudio).not.toHaveBeenCalled();
    expect(onFinishCommand).not.toHaveBeenCalled();
    act(() => FakeMediaRecorder.latest?.completeStop());

    await waitFor(() => expect(onFinishCommand).toHaveBeenCalledOnce());
    expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce();
    expect(events).toEqual(["upload", "finish"]);
    const upload = api.uploadCoachAttemptAudio.mock.calls[0][2];
    expect(upload.audio.size).toBeGreaterThan(new Blob(["first"]).size);
    expect(upload.contentSha256).toBe("275c5abc46b1fb244d1389b396c35c5edf8144654717963c426dc76b5525052c");
  });

  it("fences deferred hashing and upload when fresh authority removes the captured attempt", async () => {
    vi.useFakeTimers();
    installMedia();
    FakeMediaRecorder.deferStop = true;
    const digest = vi.spyOn(crypto.subtle, "digest");
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);

    fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce();
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId={null}
        serverState="asking"
        authorityVersion={5}
        allowedCommands={["begin_answer"]}
      />,
    );
    await act(async () => {
      FakeMediaRecorder.latest?.completeStop();
      await Promise.resolve();
    });

    expect(digest).not.toHaveBeenCalled();
    expect(api.uploadCoachAttemptAudio).not.toHaveBeenCalled();
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();
    expect(screen.queryByText("Microphone recording")).not.toBeInTheDocument();
  });

  it("silently ignores an in-flight upload rejection after fresh authority supersedes capture", async () => {
    vi.useFakeTimers();
    installMedia();
    vi.spyOn(crypto.subtle, "digest").mockResolvedValue(new Uint8Array(32).buffer);
    const upload = deferred<never>();
    api.uploadCoachAttemptAudio.mockReturnValue(upload.promise);
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);
    vi.mocked(recorderProps.onAnnouncement).mockClear();

    fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    await waitFor(() => expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce());
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId={null}
        serverState="asking"
        authorityVersion={5}
        allowedCommands={["begin_answer"]}
      />,
    );
    await act(async () => upload.reject(new Error("upload failed late")));

    expect(screen.queryByText(/captured answer is still available/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload captured answer/i })).not.toBeInTheDocument();
    expect(recorderProps.onAnnouncement).not.toHaveBeenCalled();
  });

  it("silently ignores a finish resolution after fresh authority supersedes capture", async () => {
    vi.useFakeTimers();
    installMedia();
    vi.spyOn(crypto.subtle, "digest").mockResolvedValue(new Uint8Array(32).buffer);
    const finish = deferred<boolean>();
    const recorderProps = props({ onFinishCommand: vi.fn(() => finish.promise) });
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);
    vi.mocked(recorderProps.onAnnouncement).mockClear();

    fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    await waitFor(() => expect(recorderProps.onFinishCommand).toHaveBeenCalledOnce());
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId={null}
        serverState="asking"
        authorityVersion={5}
        allowedCommands={["begin_answer"]}
      />,
    );
    await act(async () => finish.resolve(true));

    expect(screen.queryByText(/captured answer is still available/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload captured answer/i })).not.toBeInTheDocument();
    expect(recorderProps.onAnnouncement).not.toHaveBeenCalled();
  });

  it("silently ignores a finish rejection after fresh authority supersedes capture", async () => {
    vi.useFakeTimers();
    installMedia();
    vi.spyOn(crypto.subtle, "digest").mockResolvedValue(new Uint8Array(32).buffer);
    const finish = deferred<boolean>();
    const recorderProps = props({ onFinishCommand: vi.fn(() => finish.promise) });
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);
    vi.mocked(recorderProps.onAnnouncement).mockClear();

    fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    await waitFor(() => expect(recorderProps.onFinishCommand).toHaveBeenCalledOnce());
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId={null}
        serverState="asking"
        authorityVersion={5}
        allowedCommands={["begin_answer"]}
      />,
    );
    await act(async () => finish.reject(new Error("finish failed late")));

    expect(screen.queryByText(/captured answer is still available/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload captured answer/i })).not.toBeInTheDocument();
    expect(recorderProps.onAnnouncement).not.toHaveBeenCalled();
  });

  it("stops locally through final data and withholds server actions while authority is unavailable", async () => {
    vi.useFakeTimers();
    installMedia();
    FakeMediaRecorder.deferStop = true;
    vi.spyOn(crypto.subtle, "digest").mockResolvedValue(new Uint8Array(32).buffer);
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);
    FakeMediaRecorder.latest?.emitChunk(new Blob(["first"], { type: "audio/webm" }));

    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityAvailable={false}
        authorityVersion={4}
        allowedCommands={[]}
        pending={true}
      />,
    );
    expect(screen.queryByRole("button", { name: /finish audio answer/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel audio answer/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop recording and preserve captured audio" }));
    expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce();
    expect(api.uploadCoachAttemptAudio).not.toHaveBeenCalled();

    await act(async () => FakeMediaRecorder.latest?.completeStop(new Blob(["last"], { type: "audio/webm" })));
    expect(screen.getByText("Your captured audio is preserved locally while interview status is unavailable."))
      .toBeVisible();
    expect(screen.queryByRole("button", { name: /upload captured answer/i })).not.toBeInTheDocument();
    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);

    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityAvailable={true}
        authorityVersion={4}
        allowedCommands={["finish_answer", "pause", "cancel_attempt"]}
      />,
    );
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
      .click(screen.getByRole("button", { name: "Upload captured answer" }));
    await waitFor(() => expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce());
    expect(api.uploadCoachAttemptAudio.mock.calls[0][2].audio.size)
      .toBeGreaterThan(new Blob(["first"]).size);
  });

  it("pauses deferred stop and upload work across authority loss, then completes once after matching restore", async () => {
    vi.useFakeTimers();
    installMedia();
    FakeMediaRecorder.deferStop = true;
    vi.spyOn(crypto.subtle, "digest").mockResolvedValue(new Uint8Array(32).buffer);
    const upload = deferred<{
      attempt_id: string;
      upload_id: string;
      result: "completed";
      content_sha256: string;
      byte_size: number;
      mime_type: string;
      audio_retention_state: "temporary";
      contract_version: "coach_attempt_audio_upload_v1";
    }>();
    api.uploadCoachAttemptAudio.mockReturnValue(upload.promise);
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);

    fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityAvailable={false}
        authorityVersion={4}
        allowedCommands={[]}
        pending={true}
      />,
    );
    await act(async () => FakeMediaRecorder.latest?.completeStop());

    expect(crypto.subtle.digest).not.toHaveBeenCalled();
    expect(api.uploadCoachAttemptAudio).not.toHaveBeenCalled();
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();

    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityAvailable={true}
        authorityVersion={4}
        allowedCommands={["finish_answer", "pause", "cancel_attempt"]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Upload captured answer" }));
    await waitFor(() => expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce());

    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityAvailable={false}
        authorityVersion={4}
        allowedCommands={[]}
        pending={true}
      />,
    );
    await act(async () => upload.resolve({
      attempt_id: "attempt-1",
      upload_id: "upload-1",
      result: "completed",
      content_sha256: "0".repeat(64),
      byte_size: 5,
      mime_type: "audio/webm",
      audio_retention_state: "temporary",
      contract_version: "coach_attempt_audio_upload_v1",
    }));
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();

    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityAvailable={true}
        authorityVersion={4}
        allowedCommands={["finish_answer", "pause", "cancel_attempt"]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Upload captured answer" }));

    await waitFor(() => expect(recorderProps.onFinishCommand).toHaveBeenCalledOnce());
    expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce();
  });

  it.each(["resolve", "reject"] as const)(
    "requires explicit retry when authority is lost and restored before deferred hash %s",
    async (settlement) => {
      vi.useFakeTimers();
      installMedia();
      const digest = deferred<ArrayBuffer>();
      vi.spyOn(crypto.subtle, "digest")
        .mockReturnValueOnce(digest.promise)
        .mockResolvedValue(new Uint8Array(32).buffer);
      const recorderProps = props();
      const view = render(<ConversationRecorder {...recorderProps} />);
      await startRecording(recorderProps, view.rerender);

      fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
      await waitFor(() => expect(crypto.subtle.digest).toHaveBeenCalledOnce());
      view.rerender(
        <ConversationRecorder {...recorderProps} attemptId="attempt-1" serverState="listening"
          authorityAvailable={false} authorityVersion={4} allowedCommands={[]} pending={true} />,
      );
      view.rerender(
        <ConversationRecorder {...recorderProps} attemptId="attempt-1" serverState="listening"
          authorityAvailable={true} authorityVersion={4}
          allowedCommands={["finish_answer", "pause", "cancel_attempt"]} />,
      );
      await act(async () => {
        if (settlement === "resolve") digest.resolve(new Uint8Array(32).buffer);
        else digest.reject(new Error("late digest rejection"));
      });

      expect(api.uploadCoachAttemptAudio).not.toHaveBeenCalled();
      expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();
      expect(screen.queryByText(/upload error/i)).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Upload captured answer" }));

      await waitFor(() => expect(recorderProps.onFinishCommand).toHaveBeenCalledOnce());
      expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce();
    },
  );

  it.each(["resolve", "reject"] as const)(
    "requires explicit retry when authority is lost and restored before deferred upload %s",
    async (settlement) => {
      vi.useFakeTimers();
      installMedia();
      vi.spyOn(crypto.subtle, "digest").mockResolvedValue(new Uint8Array(32).buffer);
      const upload = deferred<{
        attempt_id: string;
        upload_id: string;
        result: "completed";
        content_sha256: string;
        byte_size: number;
        mime_type: string;
        audio_retention_state: "temporary";
        contract_version: "coach_attempt_audio_upload_v1";
      }>();
      const completedUpload = {
        attempt_id: "attempt-1",
        upload_id: "upload-1",
        result: "completed" as const,
        content_sha256: "0".repeat(64),
        byte_size: 5,
        mime_type: "audio/webm",
        audio_retention_state: "temporary" as const,
        contract_version: "coach_attempt_audio_upload_v1" as const,
      };
      api.uploadCoachAttemptAudio
        .mockReturnValueOnce(upload.promise)
        .mockResolvedValue(completedUpload);
      const recorderProps = props();
      const view = render(<ConversationRecorder {...recorderProps} />);
      await startRecording(recorderProps, view.rerender);

      fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
      await waitFor(() => expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce());
      view.rerender(
        <ConversationRecorder {...recorderProps} attemptId="attempt-1" serverState="listening"
          authorityAvailable={false} authorityVersion={4} allowedCommands={[]} pending={true} />,
      );
      view.rerender(
        <ConversationRecorder {...recorderProps} attemptId="attempt-1" serverState="listening"
          authorityAvailable={true} authorityVersion={4}
          allowedCommands={["finish_answer", "pause", "cancel_attempt"]} />,
      );
      await act(async () => {
        if (settlement === "resolve") upload.resolve(completedUpload);
        else upload.reject(new Error("late upload rejection"));
      });

      expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();
      expect(screen.queryByText(/upload error/i)).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Upload captured answer" }));

      await waitFor(() => expect(recorderProps.onFinishCommand).toHaveBeenCalledOnce());
      expect(api.uploadCoachAttemptAudio).toHaveBeenCalledTimes(settlement === "resolve" ? 1 : 2);
    },
  );

  it.each(["resolve", "reject"] as const)(
    "requires explicit retry when authority is lost and restored before deferred finish %s",
    async (settlement) => {
      vi.useFakeTimers();
      installMedia();
      vi.spyOn(crypto.subtle, "digest").mockResolvedValue(new Uint8Array(32).buffer);
      const finish = deferred<boolean>();
      const onFinishCommand = vi.fn()
        .mockReturnValueOnce(finish.promise)
        .mockResolvedValue(true);
      const recorderProps = props({ onFinishCommand });
      const view = render(<ConversationRecorder {...recorderProps} />);
      await startRecording(recorderProps, view.rerender);

      fireEvent.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
      await waitFor(() => expect(onFinishCommand).toHaveBeenCalledOnce());
      view.rerender(
        <ConversationRecorder {...recorderProps} attemptId="attempt-1" serverState="listening"
          authorityAvailable={false} authorityVersion={4} allowedCommands={[]} pending={true} />,
      );
      view.rerender(
        <ConversationRecorder {...recorderProps} attemptId="attempt-1" serverState="listening"
          authorityAvailable={true} authorityVersion={4}
          allowedCommands={["finish_answer", "pause", "cancel_attempt"]} />,
      );
      await act(async () => {
        if (settlement === "resolve") finish.resolve(true);
        else finish.reject(new Error("late finish rejection"));
      });

      expect(screen.queryByText(/upload error|submitted for processing/i)).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Upload captured answer" }));

      await waitFor(() => expect(onFinishCommand).toHaveBeenCalledTimes(2));
      expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce();
    },
  );

  it.each([
    { attemptId: "attempt-replacement", serverState: "listening" as const },
    { attemptId: "attempt-1", serverState: "processing_answer" as const },
  ])("never renders recovery server actions during a fresh ownership mismatch %#", async (mismatch) => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props({ onFinishCommand: vi.fn().mockResolvedValue(false) });
    let exposedInLayout = false;
    const view = render(
      <LayoutProbe inspect={null}>
        <ConversationRecorder {...recorderProps} />
      </LayoutProbe>,
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByRole("button", { name: "Start audio answer" }));
    await waitFor(() => expect(FakeMediaRecorder.latest?.state).toBe("recording"));
    view.rerender(
      <LayoutProbe inspect={null}>
        <ConversationRecorder
          {...recorderProps}
          attemptId="attempt-1"
          serverState="listening"
          authorityVersion={4}
          allowedCommands={["finish_answer", "pause", "cancel_attempt"]}
        />
      </LayoutProbe>,
    );
    await user.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    expect(await screen.findByRole("button", { name: "Upload captured answer again" })).toBeEnabled();

    view.rerender(
      <LayoutProbe inspect={() => {
        exposedInLayout = screen.queryByRole("button", { name: /upload captured answer/i }) !== null
          || screen.queryByRole("button", { name: "Discard recording and try again" }) !== null;
      }}>
        <ConversationRecorder
          {...recorderProps}
          attemptId={mismatch.attemptId}
          serverState={mismatch.serverState}
          authorityAvailable={true}
          authorityVersion={5}
          allowedCommands={["finish_answer", "pause", "cancel_attempt"]}
        />
      </LayoutProbe>,
    );

    expect(exposedInLayout).toBe(false);
    expect(recorderProps.onDiscardAndRetry).not.toHaveBeenCalled();
  });

  it("keeps one unsent blob after upload or command failure and does not re-upload a completed upload", async () => {
    vi.useFakeTimers();
    installMedia();
    const onFinishCommand = vi.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    const recorderProps = props({ onFinishCommand });
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);

    await user.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    expect(await screen.findByText(/captured answer is still available/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Upload captured answer again" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Upload captured answer again" }));
    await waitFor(() => expect(onFinishCommand).toHaveBeenCalledTimes(2));
    expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce();
  });

  it("rolls local pause back when the server rejects it and resumes only the same paused recorder", async () => {
    vi.useFakeTimers();
    installMedia();
    const onPause = vi.fn().mockResolvedValueOnce("rejected").mockResolvedValueOnce("accepted");
    const onResume = vi.fn().mockResolvedValue("accepted");
    const recorderProps = props({ onPause, onResume });
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);
    const recorder = FakeMediaRecorder.latest;

    await user.click(screen.getByRole("button", { name: "Pause audio recording" }));
    expect(recorder?.pause).toHaveBeenCalledOnce();
    expect(recorder?.resume).toHaveBeenCalledOnce();
    expect(recorder?.state).toBe("recording");

    await user.click(screen.getByRole("button", { name: "Pause audio recording" }));
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="paused"
        authorityVersion={5}
        allowedCommands={["resume"]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Resume paused audio recording" }));
    expect(onResume).toHaveBeenCalledOnce();
    expect(recorder?.resume).toHaveBeenCalledTimes(2);
    expect(recorder?.state).toBe("recording");
  });

  it("never describes a refreshed paused draft as resumed without an in-memory recorder", async () => {
    const recorderProps = props({
      attemptId: "attempt-1",
      serverState: "paused",
      allowedCommands: ["resume"],
    });
    const user = userEvent.setup();
    render(<ConversationRecorder {...recorderProps} />);

    expect(screen.getByText(/this browser no longer has the live recording/i)).toBeVisible();
    expect(screen.queryByText(/recording resumed/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resume paused audio recording/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Discard recording and try again" }));
    expect(recorderProps.onDiscardAndRetry).toHaveBeenCalledWith("attempt-1");
  });

  it("warns at five minutes and hard-stops locally at ten without automatic submission", async () => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);

    act(() => vi.advanceTimersByTime(300_000));
    expect(screen.getByText(/recording has reached five minutes/i)).toBeVisible();
    expect(recorderProps.onAnnouncement).toHaveBeenCalledWith(
      "This recording has reached five minutes. Take the time you need or finish when ready.",
    );
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();

    await act(async () => vi.advanceTimersByTime(300_000));
    expect(await screen.findByText(/recording stopped at the ten-minute limit/i)).toBeVisible();
    expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce();
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Upload captured answer" })).toBeEnabled();
  });

  it("uses monotonic active time and rechecks the hard limit after browser throttling", async () => {
    vi.useFakeTimers();
    const monotonicNow = vi.spyOn(performance, "now").mockReturnValue(0);
    installMedia();
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);

    monotonicNow.mockReturnValue(600_001);
    act(() => window.dispatchEvent(new Event("focus")));

    await waitFor(() => expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce());
    expect(screen.getByText(/recording stopped at the ten-minute limit/i)).toBeVisible();
  });

  it("excludes paused time from the monotonic hard limit and schedules only the active remainder", async () => {
    vi.useFakeTimers();
    const monotonicNow = vi.spyOn(performance, "now").mockReturnValue(0);
    installMedia();
    const recorderProps = props({ allowedCommands: ["begin_answer", "pause", "resume"] });
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);

    monotonicNow.mockReturnValue(300_000);
    await user.click(screen.getByRole("button", { name: "Pause audio recording" }));
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="paused"
        authorityVersion={5}
        allowedCommands={["resume"]}
      />,
    );
    monotonicNow.mockReturnValue(3_900_000);
    act(() => window.dispatchEvent(new Event("focus")));
    expect(FakeMediaRecorder.latest?.stop).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Resume paused audio recording" }));
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityVersion={6}
        allowedCommands={["finish_answer", "pause", "cancel_attempt"]}
      />,
    );
    monotonicNow.mockReturnValue(4_200_001);
    act(() => window.dispatchEvent(new Event("focus")));

    await waitFor(() => expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce());
  });

  it("deliberately restores focus across pause, resume, and keep-speaking control replacement", async () => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props({
      allowedCommands: ["begin_answer", "finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);

    await user.click(screen.getByRole("button", { name: "Pause audio recording" }));
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="paused"
        authorityVersion={5}
        allowedCommands={["resume"]}
      />,
    );
    expect(screen.getByRole("button", { name: "Resume paused audio recording" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Resume paused audio recording" }));
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="listening"
        authorityVersion={6}
        allowedCommands={["finish_answer", "keep_speaking", "pause", "cancel_attempt"]}
      />,
    );
    expect(screen.getByRole("button", { name: "Pause audio recording" })).toHaveFocus();

    act(() => vi.advanceTimersByTime(500));
    analyserDb = -25;
    act(() => vi.advanceTimersByTime(1600));
    analyserDb = -55;
    act(() => vi.advanceTimersByTime(9000));
    await user.click(screen.getByRole("button", { name: "Keep speaking and continue recording" }));
    expect(screen.getByRole("button", { name: "Finish audio answer while recording" })).toHaveFocus();
  });

  it("blocks unload only while local capture is unsent and cleans every browser resource on cancel", async () => {
    vi.useFakeTimers();
    const stream = installMedia();
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);

    const beforeCancel = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeCancel);
    expect(beforeCancel.defaultPrevented).toBe(true);

    await user.click(screen.getByRole("button", { name: "Cancel audio answer and discard recording" }));
    expect(recorderProps.onCancel).toHaveBeenCalledWith("attempt-1");
    expect(stream.track.stop).toHaveBeenCalledOnce();
    expect(latestAudioContext?.source.disconnect).toHaveBeenCalledOnce();
    expect(latestAudioContext?.analyser.disconnect).toHaveBeenCalledOnce();
    expect(latestAudioContext?.close).toHaveBeenCalledOnce();

    const afterCancel = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(afterCancel);
    expect(afterCancel.defaultPrevented).toBe(false);
  });

  it("keeps locally stopped audio preserved when a pending paused cancel later reports resumed authority", async () => {
    vi.useFakeTimers();
    installMedia();
    const cancel = deferred<"resumed_pending">();
    const recorderProps = props({ onCancel: vi.fn(() => cancel.promise) });
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);

    await user.click(screen.getByRole("button", { name: "Pause audio recording" }));
    const cancelClick = user.click(
      screen.getByRole("button", { name: "Cancel audio answer and discard recording" }),
    );
    await waitFor(() => expect(recorderProps.onCancel).toHaveBeenCalledOnce());
    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="paused"
        authorityAvailable={false}
        authorityVersion={5}
        allowedCommands={[]}
        pending
      />,
    );
    await user.click(screen.getByRole("button", { name: "Stop recording and preserve captured audio" }));
    expect(FakeMediaRecorder.latest?.state).toBe("inactive");

    await act(async () => cancel.resolve("resumed_pending"));
    await cancelClick;

    expect(FakeMediaRecorder.latest?.resume).not.toHaveBeenCalled();
    expect(FakeMediaRecorder.latest?.state).toBe("inactive");
    expect(screen.queryByText("Microphone recording")).not.toBeInTheDocument();
    expect(screen.getByText("Your captured audio is preserved locally while interview status is unavailable."))
      .toBeVisible();
    expect(screen.queryByText(/interview resumed.*stop locally/i)).not.toBeInTheDocument();
    expect(recorderProps.onAnnouncement).toHaveBeenLastCalledWith(
      expect.stringMatching(/stopped audio.*preserved locally/i),
    );
    expect(recorderProps.onAnnouncement).not.toHaveBeenCalledWith(
      expect.stringMatching(/recording continues locally/i),
    );
    const afterCancel = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(afterCancel);
    expect(afterCancel.defaultPrevented).toBe(true);
  });

  it("terminally stops local capture when server authority advances to processing", async () => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);

    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="processing_answer"
        authorityVersion={5}
        allowedCommands={[]}
      />,
    );

    await waitFor(() => expect(FakeMediaRecorder.latest?.stop).toHaveBeenCalledOnce());
    expect(screen.queryByText("Microphone recording")).not.toBeInTheDocument();
    const afterProcessing = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(afterProcessing);
    expect(afterProcessing.defaultPrevented).toBe(false);
  });

  it("discards a stopped unsent blob when server authority advances to processing", async () => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props({ onFinishCommand: vi.fn().mockResolvedValue(false) });
    const view = render(<ConversationRecorder {...recorderProps} />);
    const user = await startRecording(recorderProps, view.rerender);

    await user.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));
    expect(await screen.findByText(/captured answer is still available/i)).toBeVisible();

    view.rerender(
      <ConversationRecorder
        {...recorderProps}
        attemptId="attempt-1"
        serverState="processing_answer"
        authorityVersion={5}
        allowedCommands={[]}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByText(/captured answer is still available/i)).not.toBeInTheDocument();
    });
    const afterProcessing = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(afterProcessing);
    expect(afterProcessing.defaultPrevented).toBe(false);
  });

  it("handles recorder errors, releases capture resources, and keeps recovery truthful", async () => {
    vi.useFakeTimers();
    const stream = installMedia();
    const recorderProps = props();
    const view = render(<ConversationRecorder {...recorderProps} />);
    await startRecording(recorderProps, view.rerender);

    act(() => FakeMediaRecorder.latest?.emitError());

    expect(screen.getByText(/audio capture stopped because the browser reported an error/i)).toBeVisible();
    expect(stream.track.stop).toHaveBeenCalledOnce();
    expect(recorderProps.onFinishCommand).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Discard recording and try again" })).toBeEnabled();
  });

  it("restores mounted lifecycle state so StrictMode recorder errors remain visible and recoverable", async () => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props();
    const view = render(
      <StrictMode>
        <ConversationRecorder {...recorderProps} />
      </StrictMode>,
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByRole("button", { name: "Start audio answer" }));
    await waitFor(() => expect(FakeMediaRecorder.latest?.state).toBe("recording"));
    view.rerender(
      <StrictMode>
        <ConversationRecorder
          {...recorderProps}
          attemptId="attempt-1"
          serverState="listening"
          authorityVersion={4}
          allowedCommands={["finish_answer", "keep_speaking", "pause", "cancel_attempt"]}
        />
      </StrictMode>,
    );

    act(() => FakeMediaRecorder.latest?.emitError());

    expect(screen.getByText(/audio capture stopped because the browser reported an error/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Upload captured answer" })).toBeEnabled();
  });

  it("keeps StrictMode hard-stop and preserved-blob notices visible", async () => {
    vi.useFakeTimers();
    installMedia();
    const recorderProps = props({ onFinishCommand: vi.fn().mockResolvedValue(false) });
    const view = render(
      <StrictMode>
        <ConversationRecorder {...recorderProps} />
      </StrictMode>,
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByRole("button", { name: "Start audio answer" }));
    view.rerender(
      <StrictMode>
        <ConversationRecorder
          {...recorderProps}
          attemptId="attempt-1"
          serverState="listening"
          authorityVersion={4}
          allowedCommands={["finish_answer", "keep_speaking", "pause", "cancel_attempt"]}
        />
      </StrictMode>,
    );

    await act(async () => vi.advanceTimersByTime(600_000));
    expect(await screen.findByText(/recording stopped at the ten-minute limit/i)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Upload captured answer" }));
    expect(await screen.findByText(/captured answer is still available/i)).toBeVisible();
  });
});
