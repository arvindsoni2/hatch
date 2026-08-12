import '@testing-library/jest-dom';
import { Buffer } from 'node:buffer';
import { webcrypto } from 'node:crypto';
import { vi } from 'vitest';

// jsdom's Crypto implementation on Node 20 provides randomUUID but omits
// SubtleCrypto. Its ArrayBuffer also belongs to jsdom's realm, which Node 20's
// WebCrypto rejects directly, so cross the test-only realm boundary via Buffer.
const coachTestCrypto = {
  getRandomValues: webcrypto.getRandomValues.bind(webcrypto),
  randomUUID: webcrypto.randomUUID.bind(webcrypto),
  subtle: {
    digest: (algorithm: AlgorithmIdentifier, data: BufferSource) =>
      webcrypto.subtle.digest(
        algorithm,
        Buffer.from(new Uint8Array(data as ArrayBuffer)),
      ),
  },
};

Object.defineProperty(globalThis, 'crypto', {
  configurable: true,
  value: coachTestCrypto,
});
Object.defineProperty(window, 'crypto', {
  configurable: true,
  value: coachTestCrypto,
});

class CoachTestTrack {
  stop = vi.fn();
}

class CoachTestStream {
  readonly track = new CoachTestTrack();

  getTracks() {
    return [this.track];
  }
}

let coachTestStream = new CoachTestStream();
let coachTestDb = -52;

class CoachTestMediaRecorder {
  static current: CoachTestMediaRecorder | null = null;
  static deferStop = false;

  state: RecordingState = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(_stream: MediaStream) {
    CoachTestMediaRecorder.current = this;
  }

  start() {
    this.state = 'recording';
  }

  readonly pause = vi.fn(() => {
    if (this.state !== 'recording') throw new DOMException('Invalid state', 'InvalidStateError');
    this.state = 'paused';
  });

  readonly resume = vi.fn(() => {
    if (this.state !== 'paused') throw new DOMException('Invalid state', 'InvalidStateError');
    this.state = 'recording';
  });

  readonly stop = vi.fn(() => {
    if (this.state === 'inactive') return;
    this.state = 'inactive';
    if (!CoachTestMediaRecorder.deferStop) this.completeStop();
  });

  completeStop() {
    this.ondataavailable?.({ data: new Blob(['final'], { type: this.mimeType }) } as BlobEvent);
    this.onstop?.();
  }
}

class CoachTestAudioContext {
  state = 'running';
  readonly source = { connect: vi.fn(), disconnect: vi.fn() };
  readonly analyser = {
    fftSize: 2048,
    disconnect: vi.fn(),
    getFloatTimeDomainData: (values: Float32Array) => {
      values.fill(10 ** (coachTestDb / 20));
    },
  };

  createMediaStreamSource() {
    return this.source;
  }

  createAnalyser() {
    return this.analyser;
  }

  async close() {
    this.state = 'closed';
  }
}

function resetCoachMedia() {
  coachTestStream = new CoachTestStream();
  coachTestDb = -52;
  CoachTestMediaRecorder.current = null;
  CoachTestMediaRecorder.deferStop = false;
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(coachTestStream) },
  });
  Object.defineProperty(window, 'MediaRecorder', {
    configurable: true,
    value: CoachTestMediaRecorder,
  });
  Object.defineProperty(window, 'AudioContext', {
    configurable: true,
    value: CoachTestAudioContext,
  });
}

Object.defineProperty(globalThis, '__coachMediaTest', {
  configurable: true,
  value: {
    reset: resetCoachMedia,
    get stream() {
      return coachTestStream;
    },
    latestRecorder: () => CoachTestMediaRecorder.current,
    deferStop: () => {
      CoachTestMediaRecorder.deferStop = true;
    },
    completeStop: () => CoachTestMediaRecorder.current?.completeStop(),
    setAnalyserDb: (db: number) => {
      coachTestDb = db;
    },
  },
});

resetCoachMedia();

// @testing-library/dom uses `jest.advanceTimersByTime` when fake timers are
// detected. Vitest exposes the same API on `vi`, so we alias it here so that
// `waitFor` and other async utilities work correctly with vi.useFakeTimers().
(global as typeof globalThis & { jest: unknown }).jest = vi;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

global.fetch = vi.fn();

// matchMedia is not available in jsdom
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

class CoachTestResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

Object.defineProperty(window, 'ResizeObserver', {
  configurable: true,
  value: CoachTestResizeObserver,
});
