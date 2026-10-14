/**
  Available sorters.
 */
export default {
  default: (a, b) => {
    if (a.type === "directory" && b.type !== "directory") {return -1;}
    if (a.type !== "directory" && b.type === "directory") {return 1;}
    return a.name.localeCompare(b.name);
  },
};
