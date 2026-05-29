import type { AppSettings } from "../lib/api";

export type ViewKey =
  | "dashboard"
  | "library"
  | "events"
  | "downloadCenter"
  | "settings";

export type ImportFormState = {
  playlistUrl: string;
  eventName: string;
};

export type TagRuleFormState = {
  sourcePlaylistId: string;
  sourcePlaylistName: string;
  tags: string[];
};

export type MappingFormState = {
  tagName: string;
  spotifyPlaylistId: string;
  spotifyPlaylistName: string;
};

export type AppSettingKey = keyof AppSettings;
