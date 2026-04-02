#install.packages("rjson")
library("rjson")
#install.packages("jsonlite")
library("jsonlite")

setwd("~/Documents/GitHub/color_triplets")

#make json of hex code file names
filenames<- list.files("img", pattern="*.png", full.names=TRUE)
filenames2 <- as.vector(filenames) # this is the vector of file names
filenames_json <- toJSON(filenames2) 
write(filenames_json, "test.json") # save json

#make json of validation triplets
# Generate all combinations of 3 from the vector
all_combinations <- combn(filenames2, 3)

# Randomly sample 25 sets of combinations
set.seed(123)  # Set seed for reproducibility
sampled_sets <- all_combinations[, sample(ncol(all_combinations), 52)]#validation trials

check_sample <- all_combinations[, sample(ncol(all_combinations), 42)]#check trials

# View the sampled sets
#print(sampled_sets)

# Convert the sampled_sets matrix to a list of lists
sets_list <- lapply(1:ncol(sampled_sets), function(i) {
  triplet <- sampled_sets[, i]
  list(paste("head:", triplet[1]), paste("choice_1:", triplet[2]), paste("choice_2:",triplet[3]))
})

#Convert the sampled_sets matrix to a list of lists
# This time, though, choice_1 = head
#there will also be code below where choice_2 = head
check_list_1 <- lapply(1:21, function(i) {
  triplet <- check_sample[, i]
  list(paste("head:", triplet[1]), paste("choice_1:", triplet[1]), paste("choice_2:",triplet[3]), "correct_choice:0")
})

check_list_2 <- lapply(22:42, function(i) {
  triplet <- check_sample[, i]
  list(paste("head:", triplet[1]), paste("choice_1:", triplet[2]), paste("choice_2:",triplet[1]), "correct_choice:1")
})


# Format as an object without the outer array
#json_output <- gsub("\\\\", "",check_list_1)
json_output <- gsub("^\\[\n|\\]\\s*$", "",json_output)
json_output <- gsub("list(", "",json_output, fixed=TRUE)
json_output <- gsub("\\\\", "",json_output)


# Convert the list to JSON
json_output <- toJSON(sets_list, auto_unbox=TRUE, pretty = TRUE)

# View the JSON output
#cat(json_output)
write(json_output, "validationRandom.json")

