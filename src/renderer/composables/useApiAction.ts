import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

type Cleanup = () => void;

interface RunOptions<T> {
  /** Toggle busy state. Return a cleanup that is always run in `finally`. */
  busy?: () => Cleanup;
  /** Success toast text (or a builder from the result). */
  success?: string | ((result: T) => string);
  /** Side effect on success, after the toast. */
  onSuccess?: (result: T) => void;
}

/**
 * Removes the boilerplate every store action repeated: the `system.api`
 * null-check, the try/catch that turns failures into an error toast, the
 * optional success toast, and busy-flag teardown. Stores keep their own busy
 * refs (bool or keyed) and express them through the `busy` cleanup callback.
 */
export function useApiAction() {
  const system = useSystemStore();
  const ui = useUiStore();
  // The store's ref unwraps ApiClient to its public surface (no private members),
  // so derive the callback's parameter type from it rather than the class.
  type Api = NonNullable<typeof system.api>;

  async function run<T>(
    action: (api: Api) => Promise<T>,
    options: RunOptions<T> = {}
  ): Promise<T | undefined> {
    if (!system.api) return undefined;
    const cleanup = options.busy?.();
    try {
      const result = await action(system.api);
      if (options.success !== undefined) {
        ui.setMessage(
          "success",
          typeof options.success === "function" ? options.success(result) : options.success
        );
      }
      options.onSuccess?.(result);
      return result;
    } catch (error) {
      ui.setMessage("error", error instanceof Error ? error.message : String(error));
      return undefined;
    } finally {
      cleanup?.();
    }
  }

  return { run };
}
