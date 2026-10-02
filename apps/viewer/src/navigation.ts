import * as THREE from "three";
import { toThreeVec3 } from "./scene";
import type { NavigationSpec } from "./types";

const DWELL_SECONDS = 3;
const TRAVEL_SPEED = 1.2; // meters/second

interface Leg {
  points: THREE.Vector3[]; // >= 2 points to travel through, in order
  dwellAfter: number; // seconds to pause once this leg's endpoint is reached
}

/** Builds an ordered flight path from NavigationSpec: default_start_point,
 * then follows `paths` in the order given, falling back to a straight line
 * between the two endpoints' positions when a path has no `waypoints`. */
export function buildFlightPath(nav: NavigationSpec): Leg[] {
  const pointsById = new Map(nav.points.map((p) => [p.id, p]));
  const legs: Leg[] = [];

  for (const path of nav.paths) {
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
  playing = true;

  constructor(nav: NavigationSpec) {
    this.legs = buildFlightPath(nav);
  }

  get hasPath(): boolean {
    return this.legs.length > 0;
  }

  startPosition(): THREE.Vector3 {
    if (!this.hasPath) return new THREE.Vector3();
    return this.legs[0].points[0].clone();
  }

  /** Advances the walkthrough by `dt` seconds, returns the current camera
   * position and a look-at target (next point on the path). */
  update(dt: number): { position: THREE.Vector3; lookAt: THREE.Vector3 } {
    if (!this.hasPath) {
      return { position: new THREE.Vector3(), lookAt: new THREE.Vector3(0, 0, -1) };
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
    const position = a.clone().lerp(b, this.segT);
    const lookAt = b;
    return { position, lookAt };
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
