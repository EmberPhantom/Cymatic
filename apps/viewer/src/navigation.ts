import * as THREE from "three";
import { toThreeVec3 } from "./scene";
import type { NavigationSpec } from "./types";

const DWELL_SECONDS = 3;
const TRAVEL_SPEED = 1.2; // meters/second

interface Leg {
  points: THREE.Vector3[]; // >= 2 points to travel through, in order
  dwellAfter: number; // seconds to pause once this leg's endpoint is reached
}

/** Frame output written by Walkthrough.update — callers pass reusable
 * instances to avoid per-frame allocation at 60 fps. */
export interface WalkthroughFrame {
  position: THREE.Vector3;
  lookAt: THREE.Vector3;
}

/** Builds an ordered flight path from NavigationSpec: paths are rotated so
 * the walkthrough starts at `default_start_point` when it matches a path
 * origin, then follows `paths` in order, falling back to a straight line
 * between the two endpoints' positions when a path has no `waypoints`. */
export function buildFlightPath(nav: NavigationSpec): Leg[] {
  const pointsById = new Map(nav.points.map((p) => [p.id, p]));
  const legs: Leg[] = [];

  // Honor default_start_point instead of ignoring it: rotate the path list
  // so the leg departing from the start point comes first.
  const paths = [...nav.paths];
  if (nav.default_start_point) {
    const startIdx = paths.findIndex((p) => p.from === nav.default_start_point);
    if (startIdx > 0) {
      paths.push(...paths.splice(0, startIdx));
    }
  }

  for (const path of paths) {
    const from = pointsById.get(path.from);
    const to = pointsById.get(path.to);
    if (!from || !to) continue;

    const raw = path.waypoints && path.waypoints.length > 0
      ? path.waypoints
      : [from.position, to.position];

    legs.push({
      points: raw.map(toThreeVec3),
      dwellAfter: DWELL_SECONDS,
    });
  }

  return legs;
}

export class Walkthrough {
  private legs: Leg[];
  private legIndex = 0;
  private segIndex = 0;
  private segT = 0; // 0..1 progress along current segment
  private dwellRemaining = 0;
  private startOverride: THREE.Vector3 | null = null;
  playing = true;

  constructor(nav: NavigationSpec) {
    this.legs = buildFlightPath(nav);
    const start = nav.points.find((p) => p.id === nav.default_start_point);
    if (start) this.startOverride = toThreeVec3(start.position);
  }

  get hasPath(): boolean {
    return this.legs.length > 0;
  }

  startPosition(): THREE.Vector3 {
    if (this.startOverride) return this.startOverride.clone();
    if (!this.hasPath) return new THREE.Vector3();
    return this.legs[0].points[0].clone();
  }

  /** Advances the walkthrough by `dt` seconds, writing the current camera
   * position and look-at target into `out` (allocated when omitted).
   * Preallocated-temp math: no per-frame Vector3 allocation on the hot path. */
  update(dt: number, out?: WalkthroughFrame): WalkthroughFrame {
    const target = out ?? { position: new THREE.Vector3(), lookAt: new THREE.Vector3() };
    if (!this.hasPath) {
      target.position.set(0, 0, 0);
      target.lookAt.set(0, 0, -1);
      return target;
    }

    if (this.playing) {
      if (this.dwellRemaining > 0) {
        this.dwellRemaining -= dt;
      } else {
        this.advance(dt);
      }
    }

    const leg = this.legs[this.legIndex];
    const a = leg.points[this.segIndex];
    const b = leg.points[Math.min(this.segIndex + 1, leg.points.length - 1)];
    target.position.copy(a).lerp(b, this.segT);
    target.lookAt.copy(b);
    return target;
  }

  private advance(dt: number) {
    const leg = this.legs[this.legIndex];
    const a = leg.points[this.segIndex];
    const b = leg.points[Math.min(this.segIndex + 1, leg.points.length - 1)];
    const segLength = Math.max(a.distanceTo(b), 0.0001);
    this.segT += (TRAVEL_SPEED * dt) / segLength;

    if (this.segT < 1) return;

    this.segT = 0;
    this.segIndex++;

    if (this.segIndex >= leg.points.length - 1) {
      // Leg fully traversed - dwell at its endpoint, then move to the next leg.
      this.dwellRemaining = leg.dwellAfter;
      this.legIndex = (this.legIndex + 1) % this.legs.length;
      this.segIndex = 0;
    }
  }

  togglePlay() {
    this.playing = !this.playing;
  }
}
