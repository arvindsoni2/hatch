/**
 * MediaRecorder wrapper for audio/video capture during mock interviews.
 */

type RecordingType = "audio" | "video";

export class AudioVideoRecorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private startTime = 0;

  async startAudio(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this._init("audio/webm;codecs=opus");
  }

  async startVideo(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: { width: 640, height: 480, facingMode: "user" },
    });
    this._init("video/webm;codecs=vp8,opus");
  }

  async stop(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      if (!this.recorder) {
        reject(new Error("Recorder not started"));
        return;
      }
      this.recorder.ondataavailable = (e) => {
        if (e.data.size > 0) this.chunks.push(e.data);
      };
      this.recorder.onstop = () => {
        const mimeType = this.recorder?.mimeType ?? "audio/webm";
        const blob = new Blob(this.chunks, { type: mimeType });
        this._cleanup();
        resolve(blob);
      };
      this.recorder.stop();
    });
  }

  getElapsedMs(): number {
    return this.startTime ? Date.now() - this.startTime : 0;
  }

  isRecording(): boolean {
    return this.recorder?.state === "recording";
  }

  private _init(mimeType: string): void {
    if (!this.stream) return;
    this.chunks = [];
    this.startTime = Date.now();
    const supportedMime = MediaRecorder.isTypeSupported(mimeType)
      ? mimeType
      : "audio/webm";
    this.recorder = new MediaRecorder(this.stream, { mimeType: supportedMime });
    this.recorder.start(1000); // Collect chunks every 1 second
  }

  private _cleanup(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.recorder = null;
  }
}
