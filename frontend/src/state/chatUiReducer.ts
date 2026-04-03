import type { ChatAction, ChatAppState } from "./chatReducer";

export function reduceChatUi(state: ChatAppState, action: ChatAction): ChatAppState | null {
  switch (action.type) {
    case "SET_SCREEN_SIZE":
      return { ...state, isLargeScreen: action.isLargeScreen };
    case "TOGGLE_NAV":
      return { ...state, isNavOpen: !state.isNavOpen };
    case "CLOSE_NAV":
      return { ...state, isNavOpen: false };
    case "TOGGLE_DRAWER":
      return { ...state, isDrawerOpen: !state.isDrawerOpen };
    case "CLOSE_DRAWER":
      return { ...state, isDrawerOpen: false };
    case "CLOSE_PANELS":
      return { ...state, isNavOpen: false, isDrawerOpen: false };
    case "SET_URL_INPUT":
      return { ...state, urlInput: action.value };
    case "SET_CHAT_INPUT":
      return { ...state, chatInput: action.value };
    default:
      return null;
  }
}
