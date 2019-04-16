//
// Copyright © 2019 Halts. All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

#import <Foundation/Foundation.h>

@class UTMConfiguration;

NS_ASSUME_NONNULL_BEGIN

@interface UTMQemu : NSObject

- (void)pushArgv:(NSString *)arg;
- (void)startDylib:(nonnull NSString *)dylib main:(nonnull NSString *)main completion:(void(^)(BOOL,NSString *))completion;

@end

NS_ASSUME_NONNULL_END
