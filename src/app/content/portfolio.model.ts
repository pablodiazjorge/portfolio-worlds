export interface ExperienceEntry {
  readonly id: string;
  readonly period: string;
  readonly startYear: number;
  readonly endYear: number | null;
  readonly role: string;
  readonly company: string;
  readonly companyUrl: string;
  readonly contract: string;
  readonly summary: string;
  readonly description: string;
  readonly tech: readonly string[];
  readonly others: readonly string[];
}

export interface ProjectEntry {
  readonly slug: string;
  readonly title: string;
  readonly year: string | null;
  readonly tagline: string;
  readonly description: string;
  readonly cover: string;
  readonly repo: string;
  readonly demo: string | null;
  readonly tech: readonly string[];
}

export interface ContactLinks {
  readonly github: string;
  readonly linkedin: string;
  readonly cv: string;
}

export interface Portfolio {
  readonly name: string;
  readonly role: string;
  readonly focus: string;
  /** The same focus as short items, for layouts that list them. */
  readonly focusAreas: readonly string[];
  readonly intro: string;
  readonly location: string;
  readonly about: readonly string[];
  /** Newest first. */
  readonly experience: readonly ExperienceEntry[];
  readonly projects: readonly ProjectEntry[];
  readonly contact: ContactLinks;
}
