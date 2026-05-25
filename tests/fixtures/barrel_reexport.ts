// Barrel file that re-exports from submodules
export { readCookie, writeCookie } from "./cookieHelpers";
export * from "./storageHelpers";
export { basePathRewrite, getFullUrl } from "./urlHelpers";

// Also has local exports (should still be extracted as nodes)
export function localHelper() {
  return "local";
}

export const LOCAL_CONST = 42;
